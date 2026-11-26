import 'dart:async';

import 'package:flutter/foundation.dart';

import 'civi_api_service.dart';
import 'civi_audio.dart';

/// Models a message in the CIVI legal conversation.
class CiviChatMessage {
  final String text;
  final bool isUser;
  final bool isVoice;
  final String? sourceReference;

  /// Source labels from the backend, e.g. "[1] TN Co-operative Societies Act, 1983, Section 34, Page 18".
  final List<String> citations;
  final DateTime timestamp;

  /// Number of the message in the backend session; null for messages that exist only in the app
  /// (a question still being sent, or a connection error).
  final int? seq;

  /// "answered", "insufficient_evidence", "out_of_scope", "stt_failed" (assistant messages).
  final String? status;

  /// A typed question shown immediately, before the server has stored it.
  final bool pending;

  const CiviChatMessage({
    required this.text,
    required this.isUser,
    this.isVoice = false,
    this.sourceReference,
    this.citations = const [],
    required this.timestamp,
    this.seq,
    this.status,
    this.pending = false,
  });
}

/// Represents the voice interaction state shown on screen.
enum VoiceHardwareStatus {
  idle,
  recording,
  processing,
  speaking,
  replaying,
}

/// One kiosk conversation: the backend session, its messages, and voice (record / play).
///
/// The backend is the source of truth. The app polls GET /sessions/{id}/messages every
/// [pollInterval], so questions asked at the kiosk's ESP32 also appear here (Decisions 21, 37).
///
/// Voice behaviour (Decision 14):
///   - Standard mode:            typed -> text only;      microphone -> text + spoken answer
///   - Visually challenged mode: typed -> spoken answer;  microphone -> spoken answer
/// Microphone interrupts playback (18), recording stops at 60 s (20), Confirm plays the whole answer
/// and Repeat replays the last spoken version (24).
class CiviConversation extends ChangeNotifier {
  CiviConversation({
    required this.language,
    required this.speakTypedAnswers,
    CiviApiService? api,
    CiviAudio? audio,
    this.pollInterval = const Duration(seconds: 2),
  })  : _api = api ?? CiviApiService(),
        _audio = audio ?? CiviAudio();

  /// "en" or "ta"; locked for the session (Decision 16).
  final String language;

  /// True in visually challenged mode: typed answers are spoken automatically.
  final bool speakTypedAnswers;
  final Duration pollInterval;

  static const maxRecordingSeconds = 60;

  final CiviApiService _api;
  final CiviAudio _audio;

  final List<CiviChatMessage> messages = [];
  VoiceHardwareStatus status = VoiceHardwareStatus.idle;
  bool waitingForAnswer = false;
  int recordingSeconds = 0;

  /// Short messages for the screen to show (e.g. in a SnackBar).
  void Function(String message)? onNotice;

  String? _sessionId;
  Future<String>? _creatingSession;
  int _lastSeq = 0;
  bool _polling = false;
  bool _disposed = false;
  Timer? _pollTimer;
  Timer? _recordTimer;
  StreamSubscription<void>? _playbackDone;
  ({int seq, bool full})? _lastPlayed;

  bool get isTamil => language == 'ta';
  bool get appAudioEnabled => CiviAudio.enabled;

  String _t(String en, String ta) => isTamil ? ta : en;

  // ---------------------------------------------------------------------------
  // Session and polling
  // ---------------------------------------------------------------------------

  Future<void> start() async {
    _playbackDone = _audio.onPlaybackComplete.listen((_) => _setStatus(VoiceHardwareStatus.idle));
    _pollTimer = Timer.periodic(pollInterval, (_) => _sync());
    try {
      await _session();
    } catch (_) {
      // Shown when the user first asks something.
    }
  }

  Future<String> _session() async {
    if (_sessionId != null) return _sessionId!;
    _creatingSession ??= _api.createSession(language);
    try {
      _sessionId = await _creatingSession!;
      return _sessionId!;
    } finally {
      _creatingSession = null;
    }
  }

  /// Fetches new messages from the backend and replaces pending local ones.
  Future<void> _sync() async {
    final sessionId = _sessionId;
    if (sessionId == null || _polling || _disposed) return;
    _polling = true;
    try {
      final fresh = await _api.messagesAfter(sessionId, _lastSeq);
      if (fresh.isEmpty || _disposed) return;
      messages.removeWhere((m) => m.pending);
      for (final m in fresh) {
        if (m.seq <= _lastSeq) continue;
        _lastSeq = m.seq;
        messages.add(CiviChatMessage(
          text: m.text,
          isUser: m.isUser,
          isVoice: m.isVoice,
          citations: m.citations,
          timestamp: DateTime.now(),
          seq: m.seq,
          status: m.status,
        ));
      }
      _notify();
    } on CiviApiException catch (e) {
      if (e.sessionExpired) _sessionId = null; // 30 minutes without activity (Decision 31)
    } catch (_) {
      // Offline for a moment: try again on the next poll.
    } finally {
      _polling = false;
    }
  }

  /// Starts a fresh conversation (Back / Reset).
  Future<void> reset() async {
    await _stopVoice();
    final old = _sessionId;
    _sessionId = null;
    _lastSeq = 0;
    _lastPlayed = null;
    messages.clear();
    waitingForAnswer = false;
    _notify();
    if (old != null) unawaited(_api.endSession(old));
    try {
      await _session();
    } catch (_) {
      // Retried on the next question.
    }
  }

  // ---------------------------------------------------------------------------
  // Typed questions
  // ---------------------------------------------------------------------------

  Future<void> sendText(String text) async {
    final question = text.trim();
    if (question.isEmpty || waitingForAnswer) return;
    messages.add(CiviChatMessage(text: question, isUser: true, timestamp: DateTime.now(), pending: true));
    waitingForAnswer = true;
    _notify();
    try {
      final answer = await _withSession((id) => _api.chat(sessionId: id, message: question, language: language));
      await _sync();
      if (speakTypedAnswers) await _play(answer.assistantSeq);
    } catch (e) {
      _addLocalError(e);
    } finally {
      waitingForAnswer = false;
      _notify();
    }
  }

  // ---------------------------------------------------------------------------
  // Voice (device microphone as a stand-in for the ESP32)
  // ---------------------------------------------------------------------------

  /// The Microphone button: first press records, second press sends (Decision 19).
  Future<void> micPressed() async {
    switch (status) {
      case VoiceHardwareStatus.recording:
        await _stopAndSend();
      case VoiceHardwareStatus.processing:
        return; // already answering
      case VoiceHardwareStatus.idle:
      case VoiceHardwareStatus.speaking:
      case VoiceHardwareStatus.replaying:
        if (!appAudioEnabled) {
          onNotice?.call(_t('Please use the Mic button on the kiosk.', 'கியோஸ்கில் உள்ள மைக் பொத்தானைப் பயன்படுத்தவும்.'));
          return;
        }
        if (waitingForAnswer) return;
        await _audio.stopPlayback(); // the microphone interrupts playback (Decision 18)
        await _startRecording();
    }
  }

  Future<void> _startRecording() async {
    try {
      if (!await _audio.hasMicrophonePermission()) {
        onNotice?.call(_t('Microphone permission is needed to ask by voice.',
            'குரல் மூலம் கேட்க மைக் அனுமதி தேவை.'));
        return;
      }
      await _audio.startRecording();
    } catch (e) {
      onNotice?.call(_t('Could not start the microphone: $e', 'மைக்கைத் தொடங்க முடியவில்லை: $e'));
      return;
    }
    recordingSeconds = 0;
    _setStatus(VoiceHardwareStatus.recording);
    _recordTimer?.cancel();
    _recordTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      recordingSeconds++;
      _notify();
      if (recordingSeconds >= maxRecordingSeconds) {
        unawaited(_stopAndSend()); // stop automatically at 60 s and send (Decision 20)
      }
    });
  }

  Future<void> _stopAndSend() async {
    _recordTimer?.cancel();
    if (status != VoiceHardwareStatus.recording) return;
    _setStatus(VoiceHardwareStatus.processing);
    waitingForAnswer = true;
    _notify();
    try {
      final wav = await _audio.stopRecording();
      if (wav == null || wav.length < 3200) {
        // Less than 0.1 s: the button was pressed twice by accident.
        onNotice?.call(_t('No question was recorded.', 'கேள்வி எதுவும் பதிவாகவில்லை.'));
        _setStatus(VoiceHardwareStatus.idle);
        return;
      }
      final answer = await _withSession((id) => _api.voiceQuery(sessionId: id, wav: wav));
      await _sync();
      // Spoken questions always get a spoken answer; a "please repeat" prompt is spoken too (Decision 17).
      await _play(answer.assistantSeq);
    } catch (e) {
      _addLocalError(e);
      _setStatus(VoiceHardwareStatus.idle);
    } finally {
      waitingForAnswer = false;
      if (status == VoiceHardwareStatus.processing) _setStatus(VoiceHardwareStatus.idle);
      _notify();
    }
  }

  /// Repeat Voice: replays the last spoken version, or the latest answer's summary (Decision 24).
  Future<void> repeat() async {
    if (status == VoiceHardwareStatus.recording || status == VoiceHardwareStatus.processing) return;
    final last = _lastPlayed;
    if (last != null) {
      await _play(last.seq, full: last.full, replay: true);
      return;
    }
    final seq = _latestAnswerSeq();
    if (seq != null) await _play(seq, replay: true);
  }

  /// Confirm: speaks the complete latest answer instead of the short summary (Decision 24).
  Future<void> confirmFullAnswer() async {
    if (status == VoiceHardwareStatus.recording || status == VoiceHardwareStatus.processing) return;
    final seq = _latestAnswerSeq();
    if (seq != null) await _play(seq, full: true);
  }

  int? _latestAnswerSeq() {
    for (final m in messages.reversed) {
      if (!m.isUser && m.seq != null) return m.seq;
    }
    return null;
  }

  Future<void> _play(int seq, {bool full = false, bool replay = false}) async {
    if (!appAudioEnabled || seq <= 0) return; // the ESP32 speaks instead (Phase 7)
    final sessionId = _sessionId;
    if (sessionId == null) return;
    _lastPlayed = (seq: seq, full: full);
    _setStatus(replay ? VoiceHardwareStatus.replaying : VoiceHardwareStatus.speaking);
    try {
      await _audio.play(_api.audioUrl(sessionId, seq, full: full));
    } catch (e) {
      _setStatus(VoiceHardwareStatus.idle);
      onNotice?.call(_t('Could not play the spoken answer. Is the speech service running?',
          'பதிலை ஒலிக்க முடியவில்லை. பேச்சு சேவை இயங்குகிறதா?'));
    }
  }

  Future<void> _stopVoice() async {
    _recordTimer?.cancel();
    if (status == VoiceHardwareStatus.recording) await _audio.cancelRecording();
    await _audio.stopPlayback();
    _setStatus(VoiceHardwareStatus.idle);
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  /// Runs a request with the current session; if the session expired, starts a new one and retries once.
  Future<T> _withSession<T>(Future<T> Function(String sessionId) request) async {
    final id = await _session();
    try {
      return await request(id);
    } on CiviApiException catch (e) {
      if (!e.sessionExpired) rethrow;
      _sessionId = null;
      _lastSeq = 0;
      return request(await _session());
    }
  }

  void _addLocalError(Object error) {
    final String text;
    if (error is CiviApiException) {
      text = switch (error.code) {
        'speech_unavailable' => _t(
            'Voice is not available right now (the speech service is not running). Please type your question.',
            'குரல் வசதி இப்போது இல்லை (பேச்சு சேவை இயங்கவில்லை). உங்கள் கேள்வியைத் தட்டச்சு செய்யவும்.'),
        'service_unavailable' || 'upstream_error' => _t(
            'The answer service is busy right now. Please try again in a minute.',
            'பதில் சேவை இப்போது பரபரப்பாக உள்ளது. ஒரு நிமிடம் கழித்து மீண்டும் முயலவும்.'),
        _ => _t('Unable to get an answer: ${error.message}', 'பதில் பெற முடியவில்லை: ${error.message}'),
      };
    } else {
      text = _t('Unable to reach the CIVI server. Check the Wi-Fi connection and server address.',
          'சேவையகத்தை அணுக முடியவில்லை. Wi-Fi இணைப்பு மற்றும் சேவையகத்தின் முகவரியைச் சரிபார்க்கவும்.');
    }
    // The question itself stays visible (it is replaced by the server's copy on the next sync, if stored).
    messages.add(CiviChatMessage(text: text, isUser: false, timestamp: DateTime.now()));
  }

  void _setStatus(VoiceHardwareStatus value) {
    if (status == value) return;
    status = value;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _pollTimer?.cancel();
    _recordTimer?.cancel();
    _playbackDone?.cancel();
    final id = _sessionId;
    if (id != null) unawaited(_api.endSession(id));
    unawaited(_audio.dispose());
    super.dispose();
  }
}

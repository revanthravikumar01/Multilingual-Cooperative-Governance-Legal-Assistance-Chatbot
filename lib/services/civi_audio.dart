import 'dart:async';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// The device's own microphone and speaker, used as a stand-in until the kiosk's ESP32 takes over
/// (Decision 36 gives the real microphone and speaker to the ESP32, Phase 7).
///
/// Turn it off when the ESP32 is connected:  --dart-define=CIVI_APP_AUDIO=false
/// Recordings use exactly the kiosk format the backend expects: 16 kHz, 16-bit, mono WAV.
class CiviAudio {
  static const enabled = bool.fromEnvironment('CIVI_APP_AUDIO', defaultValue: true);

  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer _player = AudioPlayer();

  /// Fires when an answer finishes playing.
  Stream<void> get onPlaybackComplete => _player.onPlayerComplete;

  Future<bool> hasMicrophonePermission() => _recorder.hasPermission();

  Future<void> startRecording() async {
    // On the web the recording is kept in memory, so no file path is needed.
    final path = kIsWeb ? '' : '${(await getTemporaryDirectory()).path}/civi_question.wav';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.wav, sampleRate: 16000, numChannels: 1),
      path: path,
    );
  }

  /// Stops recording and returns the WAV bytes (null if nothing was recorded).
  Future<Uint8List?> stopRecording() async {
    final path = await _recorder.stop();
    if (path == null || path.isEmpty) return null;
    if (kIsWeb) {
      // In a browser the recording is an in-memory "blob:" address.
      return (await http.get(Uri.parse(path))).bodyBytes;
    }
    return XFile.fileSystem(path: path).readAsBytes();
  }

  Future<void> cancelRecording() async {
    try {
      await _recorder.cancel();
    } catch (_) {
      // Not recording.
    }
  }

  /// Plays a spoken answer from the backend; stops anything already playing (Decision 18).
  Future<void> play(String url) async {
    await _player.stop();
    await _player.play(UrlSource(url));
  }

  Future<void> stopPlayback() async {
    try {
      await _player.stop();
    } catch (_) {
      // Nothing playing.
    }
  }

  Future<void> dispose() async {
    await cancelRecording();
    await _recorder.dispose();
    await _player.dispose();
  }
}

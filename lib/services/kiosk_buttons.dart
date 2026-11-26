import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart' show WidgetsBinding;
import 'package:http/http.dart' as http;

import 'civi_api_service.dart';

/// A press of one of the kiosk's six physical buttons, or a change in what the ESP32's
/// microphone/speaker is doing.
class KioskEvent {
  const KioskEvent({this.button, this.status});

  /// language | confirm | back | repeat | mic | accessibility
  final String? button;

  /// recording | processing | speaking | idle (the ESP32 records and plays audio itself)
  final String? status;
}

/// Receives the kiosk's button presses from the backend (Decision 34: the ESP32 talks to the backend,
/// the app follows). Polls GET /kiosks/{kiosk_id}/events about twice a second.
///
/// Each screen listens to [events] and runs the same action as its keyboard shortcut.
class KioskButtons {
  KioskButtons._();

  static final KioskButtons instance = KioskButtons._();

  static const pollInterval = Duration(milliseconds: 400);
  static const gapBetweenPresses = Duration(milliseconds: 600);

  final StreamController<KioskEvent> _controller = StreamController<KioskEvent>.broadcast();
  final http.Client _http = http.Client();
  Timer? _timer;
  int? _lastSeq;
  bool _busy = false;

  Stream<KioskEvent> get events => _controller.stream;

  /// Starts polling (safe to call more than once). Does nothing if no backend address is set.
  void start() {
    if (_timer != null || CiviApiService.baseUrl.isEmpty) return;
    _timer = Timer.periodic(pollInterval, (_) => _poll());
  }

  /// Waits until the previous press has taken effect on screen: a short pause for screen transitions,
  /// then two drawn frames (so a newly opened screen exists and listens). If the app isn't drawing
  /// (e.g. a hidden browser tab), presses wait here instead of being lost.
  Future<void> _letScreenCatchUp() async {
    await Future<void>.delayed(gapBetweenPresses);
    await WidgetsBinding.instance.endOfFrame;
    await WidgetsBinding.instance.endOfFrame;
  }

  Future<void> _poll() async {
    if (_busy) return;
    _busy = true;
    try {
      // First call: -1 = "where are we now?", so presses from before the app started are ignored.
      final uri = Uri.parse('${CiviApiService.baseUrl}/api/v1/kiosks/${CiviApiService.kioskId}/events')
          .replace(queryParameters: {'after': '${_lastSeq ?? -1}'});
      final response = await _http.get(uri).timeout(const Duration(seconds: 5));
      if (response.statusCode != 200) return;
      final body = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
      final events = body['events'];
      final first = _lastSeq == null;
      _lastSeq = (body['latest_seq'] as num?)?.toInt() ?? _lastSeq;
      if (!first && events is List) {
        var delay = false;
        for (final e in events) {
          if (e is! Map) continue;
          // Several presses can arrive together (slow Wi-Fi, a busy phone). Hand them over one at a
          // time, so a press that changes screen finishes before the next press is handled.
          if (delay) await _letScreenCatchUp();
          _controller.add(KioskEvent(button: e['button'] as String?, status: e['status'] as String?));
          delay = e['button'] != null;
        }
      }
    } catch (_) {
      // Backend not reachable for a moment: try again on the next tick.
    } finally {
      _busy = false;
    }
  }
}

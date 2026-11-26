import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

/// HTTP client for the CIVI backend (see backend/API_CONTRACT.md).
///
/// Launch the app with the laptop's Wi-Fi address, for example:
///   --dart-define=CIVI_API_BASE_URL=http://192.168.1.20:8000
/// Optional: --dart-define=CIVI_KIOSK_ID=kiosk-1 (links the session to the kiosk's ESP32, Phase 7).
class CiviApiService {
  CiviApiService({http.Client? client}) : _http = client ?? http.Client();

  static const baseUrl = String.fromEnvironment('CIVI_API_BASE_URL');
  static const kioskId = String.fromEnvironment('CIVI_KIOSK_ID', defaultValue: 'kiosk-1');

  /// Searching the law, asking Gemini (with retries) and recognising speech can take a while.
  static const _answerTimeout = Duration(seconds: 120);
  static const _shortTimeout = Duration(seconds: 15);

  final http.Client _http;

  Uri _uri(String path, [Map<String, String>? query]) {
    if (baseUrl.isEmpty) {
      throw const CiviApiException(
        'CIVI_API_BASE_URL is not set. Launch the app with your laptop Wi-Fi address.',
        code: 'not_configured',
      );
    }
    return Uri.parse('$baseUrl/api/v1$path').replace(queryParameters: query);
  }

  /// Full address of the spoken version of an answer (Decision 24: summary or full).
  String audioUrl(String sessionId, int seq, {bool full = false}) =>
      _uri('/voice/audio/$sessionId/$seq', {'variant': full ? 'full' : 'summary'}).toString();

  Future<String> createSession(String language) async {
    final response = await _http
        .post(
          _uri('/sessions'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'language': language, 'kiosk_id': kioskId}),
        )
        .timeout(_shortTimeout);
    final body = _check(response, expected: 201);
    return body['session_id'] as String;
  }

  /// Ends a session on the server (best effort: it would expire after 30 minutes anyway).
  Future<void> endSession(String sessionId) async {
    try {
      await _http.delete(_uri('/sessions/$sessionId')).timeout(_shortTimeout);
    } catch (_) {
      // Ignore: the session expires on its own.
    }
  }

  Future<CiviAnswer> chat({required String sessionId, required String message, required String language}) async {
    final response = await _http
        .post(
          _uri('/chat'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'message': message, 'language': language, 'session_id': sessionId}),
        )
        .timeout(_answerTimeout);
    return CiviAnswer.fromJson(_check(response));
  }

  /// Sends a recorded question (16 kHz, 16-bit, mono WAV, ≤ 60 s) — the same call the ESP32 makes.
  Future<CiviAnswer> voiceQuery({required String sessionId, required Uint8List wav}) async {
    final response = await _http
        .post(
          _uri('/voice/query'),
          headers: {'Content-Type': 'audio/wav', 'X-Session-Id': sessionId},
          body: wav,
        )
        .timeout(_answerTimeout);
    return CiviAnswer.fromJson(_check(response));
  }

  /// Messages newer than [afterSeq] — how the app learns about questions asked at the ESP32 (Decision 37).
  Future<List<CiviRemoteMessage>> messagesAfter(String sessionId, int afterSeq) async {
    final response = await _http
        .get(_uri('/sessions/$sessionId/messages', {'after': '$afterSeq'}))
        .timeout(_shortTimeout);
    final body = _check(response);
    final raw = body['messages'];
    if (raw is! List) return const [];
    return [for (final item in raw) if (item is Map) CiviRemoteMessage.fromJson(Map<String, dynamic>.from(item))];
  }

  Map<String, dynamic> _check(http.Response response, {int expected = 200}) {
    Map<String, dynamic>? body;
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map) body = Map<String, dynamic>.from(decoded);
    } catch (_) {
      // Not JSON.
    }
    if (response.statusCode == expected && body != null) return body;
    final error = body?['error'];
    if (error is Map) {
      throw CiviApiException(
        '${error['message'] ?? 'Server error'}',
        code: '${error['code'] ?? ''}',
        statusCode: response.statusCode,
      );
    }
    throw CiviApiException('Server returned HTTP ${response.statusCode}.', statusCode: response.statusCode);
  }
}

/// Reply to a typed (/chat) or spoken (/voice/query) question.
class CiviAnswer {
  const CiviAnswer({
    required this.answer,
    required this.status,
    required this.citations,
    required this.assistantSeq,
    this.userSeq,
    this.transcript,
    this.spokenSummary,
  });

  factory CiviAnswer.fromJson(Map<String, dynamic> json) => CiviAnswer(
        answer: '${json['answer'] ?? ''}',
        status: '${json['status'] ?? 'answered'}',
        citations: _labels(json['citations']),
        assistantSeq: (json['assistant_message_seq'] as num?)?.toInt() ?? 0,
        userSeq: (json['user_message_seq'] as num?)?.toInt(),
        transcript: json['transcript'] as String?,
        spokenSummary: json['spoken_summary'] as String?,
      );

  final String answer;

  /// "answered", "insufficient_evidence", "out_of_scope" or "stt_failed" (speech not recognised).
  final String status;
  final List<String> citations;
  final int assistantSeq;
  final int? userSeq;
  final String? transcript;
  final String? spokenSummary;
}

/// A message stored in the backend session (typed in the app or spoken at the kiosk).
class CiviRemoteMessage {
  const CiviRemoteMessage({
    required this.seq,
    required this.isUser,
    required this.text,
    required this.isVoice,
    required this.citations,
    this.status,
  });

  factory CiviRemoteMessage.fromJson(Map<String, dynamic> json) => CiviRemoteMessage(
        seq: (json['seq'] as num).toInt(),
        isUser: json['role'] == 'user',
        text: '${json['text'] ?? ''}',
        isVoice: json['source'] == 'voice',
        citations: _labels(json['citations']),
        status: json['status'] as String?,
      );

  final int seq;
  final bool isUser;
  final String text;
  final bool isVoice;
  final List<String> citations;
  final String? status;
}

List<String> _labels(Object? raw) => [
      if (raw is List)
        for (final item in raw)
          if (item is Map && item['label'] is String) item['label'] as String,
    ];

class CiviApiException implements Exception {
  const CiviApiException(this.message, {this.code = '', this.statusCode});

  final String message;
  final String code;
  final int? statusCode;

  bool get sessionExpired => code == 'session_not_found';

  @override
  String toString() => message;
}

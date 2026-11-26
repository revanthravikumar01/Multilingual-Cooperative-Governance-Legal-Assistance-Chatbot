import 'dart:convert';

import 'package:http/http.dart' as http;

/// HTTP client for the CIVI backend (see backend/API_CONTRACT.md).
///
/// Supply the laptop's LAN address when launching the app, for example:
/// --dart-define=CIVI_API_BASE_URL=http://192.168.1.20:8000
///
/// One instance belongs to one chat screen. It remembers the backend session, so
/// follow-up questions ("and for members?") are understood (Decision 11).
class CiviApiService {
  static const _baseUrl = String.fromEnvironment('CIVI_API_BASE_URL');

  /// Searching the knowledge base and asking Gemini (with retries) can take a while.
  static const _timeout = Duration(seconds: 60);

  String? _sessionId;

  /// Forget the current conversation; the next question starts a new session.
  void resetSession() {
    _sessionId = null;
  }

  Future<CiviChatResponse> sendTextMessage({
    required String message,
    required String language,
  }) async {
    if (_baseUrl.isEmpty) {
      throw const CiviApiException(
        'CIVI_API_BASE_URL is not set. Launch the app with your laptop Wi-Fi address.',
      );
    }

    var response = await _postChat(message, language, _sessionId);

    // The session expired after 30 minutes of inactivity (Decision 31): start a new one.
    if (response.statusCode == 404 && _errorCode(response) == 'session_not_found') {
      _sessionId = null;
      response = await _postChat(message, language, null);
    }

    if (response.statusCode != 200) {
      throw CiviApiException(
        _errorMessage(response) ?? 'Server returned HTTP ${response.statusCode}.',
      );
    }

    final body = jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    final answer = body['answer'];
    if (answer is! String || answer.isEmpty) {
      throw const CiviApiException('Server returned an invalid chat response.');
    }

    final sessionId = body['session_id'];
    if (sessionId is String && sessionId.isNotEmpty) {
      _sessionId = sessionId;
    }

    final citations = <String>[];
    final rawCitations = body['citations'];
    if (rawCitations is List) {
      for (final item in rawCitations) {
        if (item is Map && item['label'] is String) {
          citations.add(item['label'] as String);
        }
      }
    }

    return CiviChatResponse(
      answer: answer,
      status: body['status'] is String ? body['status'] as String : 'answered',
      citations: citations,
      spokenSummary: body['spoken_summary'] is String ? body['spoken_summary'] as String : null,
    );
  }

  Future<http.Response> _postChat(String message, String language, String? sessionId) {
    return http
        .post(
          Uri.parse('$_baseUrl/api/v1/chat'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({
            'message': message,
            'language': language,
            'session_id': ?sessionId,
          }),
        )
        .timeout(_timeout);
  }

  static Map<String, dynamic>? _error(http.Response response) {
    try {
      final body = jsonDecode(utf8.decode(response.bodyBytes));
      if (body is Map && body['error'] is Map) {
        return Map<String, dynamic>.from(body['error'] as Map);
      }
    } catch (_) {
      // Not a JSON error body.
    }
    return null;
  }

  static String? _errorCode(http.Response response) => _error(response)?['code'] as String?;

  static String? _errorMessage(http.Response response) => _error(response)?['message'] as String?;
}

class CiviChatResponse {
  const CiviChatResponse({
    required this.answer,
    this.status = 'answered',
    this.citations = const [],
    this.spokenSummary,
  });

  final String answer;

  /// "answered", "insufficient_evidence" or "out_of_scope".
  final String status;

  /// Compact source labels built by the backend, e.g.
  /// "[1] TN Co-operative Societies Act, 1983, Section 34, Page 18".
  final List<String> citations;

  /// Short version of a long answer for speech (Phase 4), or null.
  final String? spokenSummary;
}

class CiviApiException implements Exception {
  const CiviApiException(this.message);

  final String message;
}

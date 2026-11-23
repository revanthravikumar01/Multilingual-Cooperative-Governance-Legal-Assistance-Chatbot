import 'dart:convert';

import 'package:http/http.dart' as http;

/// HTTP client for the first CIVI backend integration phase.
///
/// Supply the laptop's LAN address when launching the app, for example:
/// --dart-define=CIVI_API_BASE_URL=http://192.168.1.20:8000
class CiviApiService {
  static const _baseUrl = String.fromEnvironment('CIVI_API_BASE_URL');

  Future<CiviChatResponse> sendTextMessage({
    required String message,
    required String language,
  }) async {
    if (_baseUrl.isEmpty) {
      throw const CiviApiException(
        'CIVI_API_BASE_URL is not set. Launch the app with your laptop Wi-Fi address.',
      );
    }

    final response = await http
        .post(
          Uri.parse('$_baseUrl/api/v1/chat'),
          headers: const {'Content-Type': 'application/json'},
          body: jsonEncode({'message': message, 'language': language}),
        )
        .timeout(const Duration(seconds: 15));

    if (response.statusCode != 200) {
      throw CiviApiException('Server returned HTTP ${response.statusCode}.');
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final answer = body['answer'];
    if (answer is! String || answer.isEmpty) {
      throw const CiviApiException('Server returned an invalid chat response.');
    }

    return CiviChatResponse(answer: answer);
  }
}

class CiviChatResponse {
  const CiviChatResponse({required this.answer});

  final String answer;
}

class CiviApiException implements Exception {
  const CiviApiException(this.message);

  final String message;
}

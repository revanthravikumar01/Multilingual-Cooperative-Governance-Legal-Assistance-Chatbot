import 'package:flutter_test/flutter_test.dart';

import 'package:multilingual_cooperative_governance_legal_assistance_chatbot/main.dart';
import 'package:multilingual_cooperative_governance_legal_assistance_chatbot/boot_screen.dart';

void main() {
  testWidgets('Boot screen loads smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    // Verify BootScreen is rendered
    expect(find.byType(BootScreen), findsOneWidget);
  });
}

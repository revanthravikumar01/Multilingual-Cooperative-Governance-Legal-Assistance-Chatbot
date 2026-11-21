import 'dart:async';
import 'package:material_ui/material_ui.dart';
import 'language_selection_screen.dart';

/// Boot / Splash screen for CIVI (Multilingual Cooperative Governance & Legal Assistance Chatbot).
///
/// Features:
/// - Full-screen linear gradient background from Deep Forest (#124E43) to Emerald (#2D8C75).
/// - Centered new CIVI brand logo with its aspect ratio strictly preserved.
/// - Pure smooth 2-second fade-in animation (opacity 0 -> 1) with no scale, rotation, or bounce.
/// - Fully visible logo held in place from 2s to 5s.
/// - Exact 5-second total duration before automatically navigating to the Language Selection screen.
class BootScreen extends StatefulWidget {
  const BootScreen({super.key});

  @override
  State<BootScreen> createState() => _BootScreenState();
}

class _BootScreenState extends State<BootScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _animationController;
  late final Animation<double> _fadeAnimation;

  Timer? _navigationTimer;
  bool _hasNavigated = false;

  @override
  void initState() {
    super.initState();

    // 1. Exactly 2-second duration for the smooth fade-in animation
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    );

    _fadeAnimation = CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeInOut,
    );

    // Start the fade-in animation immediately upon mounting
    _animationController.forward();

    // 2. Exactly 5-second total screen duration before navigating
    _navigationTimer = Timer(const Duration(seconds: 5), _navigateToLanguageScreen);
  }

  void _navigateToLanguageScreen() {
    if (!mounted || _hasNavigated) return;
    _hasNavigated = true;

    Navigator.of(context).pushReplacement(
      PageRouteBuilder(
        pageBuilder: (context, animation, secondaryAnimation) =>
            const LanguageSelectionScreen(),
        transitionsBuilder: (context, animation, secondaryAnimation, child) {
          return FadeTransition(opacity: animation, child: child);
        },
        transitionDuration: const Duration(milliseconds: 500),
      ),
    );
  }

  @override
  void dispose() {
    _navigationTimer?.cancel();
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final screenWidth = mediaQuery.size.width;
    final screenHeight = mediaQuery.size.height;

    // Responsive logo sizing:
    // Appropriately constrained for mobile and desktop screens while strictly preserving aspect ratio.
    final double widthConstraint = screenWidth * 0.78;
    final double heightConstraint = (screenHeight * 0.42) * 1.5;
    final double responsiveLogoWidth =
        (widthConstraint < heightConstraint ? widthConstraint : heightConstraint)
            .clamp(180.0, 520.0);

    return Scaffold(
      body: Container(
        width: double.infinity,
        height: double.infinity,
        decoration: const BoxDecoration(
          // Smooth linear gradient from Deep Forest (#124E43) to Emerald (#2D8C75)
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(0xFF124E43), // Deep Forest
              Color(0xFF2D8C75), // Emerald
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: FadeTransition(
              opacity: _fadeAnimation,
              child: Image.asset(
                'assets/images/civi_logo.png',
                width: responsiveLogoWidth,
                fit: BoxFit.contain,
              errorBuilder: (context, error, stackTrace) {
                return Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 16,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: const Color(0xFFA3E4D7).withValues(alpha: 0.3),
                    ),
                  ),
                  child: const Text(
                    'Logo asset missing:\nassets/images/civi_logo.png',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Colors.white70,
                      fontSize: 12,
                    ),
                  ),
                );
              },
            ),
          ),
        ),
      ),
    ),
  );
  }
}

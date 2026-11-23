import 'dart:async';
import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';
import 'language_selection_screen.dart';

/// Supported accessibility modes in CIVI.
enum CiviAccessibilityMode { standard, visuallyChallenged }

/// Accessibility Confirmation Screen for CIVI.
///
/// Features:
/// - Maintains CIVI color theme: Deep Forest (#124E43), Emerald (#2D8C75), White, Light Green (#EAF3EF).
/// - Dynamic Island styled panels for Standard Mode and Visually Challenged Mode.
/// - Full localization for English and Tamil based on previous language selection.
/// - Modular hooks for hardware events:
///     - [switchAccessibilityMode]: Cycles between Standard and Visually Challenged modes.
///     - [confirmMode]: Single-press YES confirmation.
///     - [activateDedicatedVisuallyChallengedMode]: Direct one-touch trigger with spoken announcement.
/// - Keyboard shortcuts: 'M' (Mode switch), 'Y' / Enter (YES confirm), 'V' (Dedicated Visually Challenged button).
class AccessibilityConfirmationScreen extends StatefulWidget {
  final CiviLanguage? initialLanguage;

  const AccessibilityConfirmationScreen({super.key, this.initialLanguage});

  @override
  State<AccessibilityConfirmationScreen> createState() =>
      _AccessibilityConfirmationScreenState();
}

class _AccessibilityConfirmationScreenState
    extends State<AccessibilityConfirmationScreen>
    with SingleTickerProviderStateMixin {
  // Theme palette
  static const Color _deepForest = Color(0xFF124E43);
  static const Color _emerald = Color(0xFF2D8C75);
  static const Color _lightGreen = Color(0xFFEAF3EF);

  // Active state
  late CiviLanguage _language;
  CiviAccessibilityMode _selectedMode = CiviAccessibilityMode.standard;
  CiviAccessibilityMode? _hoveredMode;

  bool _isAnnouncing = false;
  String? _announcementText;
  Timer? _announcementTimer;

  // Background ambient animation
  late final AnimationController _bgController;
  late final Animation<Alignment> _topAlignmentAnim;
  late final Animation<Alignment> _bottomAlignmentAnim;

  final FocusNode _focusNode = FocusNode();

  @override
  void initState() {
    super.initState();
    _language = widget.initialLanguage ?? CiviLanguage.english;

    _bgController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat(reverse: true);

    _topAlignmentAnim = AlignmentTween(
      begin: Alignment.topCenter,
      end: Alignment.topLeft,
    ).animate(CurvedAnimation(parent: _bgController, curve: Curves.easeInOut));

    _bottomAlignmentAnim = AlignmentTween(
      begin: Alignment.bottomCenter,
      end: Alignment.bottomRight,
    ).animate(CurvedAnimation(parent: _bgController, curve: Curves.easeInOut));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is CiviLanguage) {
      _language = args;
    }
  }

  @override
  void dispose() {
    _announcementTimer?.cancel();
    _focusNode.dispose();
    _bgController.dispose();
    super.dispose();
  }

  /// Cycles between Standard and Visually Challenged Mode.
  /// Callable by physical Mode Selector button.
  void switchAccessibilityMode() {
    if (_isAnnouncing) return;
    setState(() {
      _selectedMode = (_selectedMode == CiviAccessibilityMode.standard)
          ? CiviAccessibilityMode.visuallyChallenged
          : CiviAccessibilityMode.standard;
    });
  }

  /// Directly selects a specific accessibility mode.
  void selectMode(CiviAccessibilityMode mode) {
    if (_isAnnouncing) return;
    if (_selectedMode != mode) {
      setState(() {
        _selectedMode = mode;
      });
    }
  }

  /// Confirms the currently selected mode with a single YES press.
  void confirmMode() {
    if (_isAnnouncing) return;
    _navigateToChatbot(_selectedMode);
  }

  /// Triggered immediately by the dedicated physical Visually Challenged button.
  /// Activates mode directly without requiring manual option traversal or extra YES press.
  void activateDedicatedVisuallyChallengedMode() {
    if (_isAnnouncing) return;

    setState(() {
      _selectedMode = CiviAccessibilityMode.visuallyChallenged;
      _isAnnouncing = true;
      _announcementText = _language == CiviLanguage.english
          ? 'Visually Challenged Mode activated. Welcome to CIVI.'
          : 'பார்வைக் குறைபாடு உள்ளவர்களுக்கான பயன்முறை செயல்படுத்தப்பட்டது. CIVI-க்கு வரவேற்கிறோம்.';
    });

    // Simulate spoken TTS announcement playback duration before proceeding to Chatbot
    _announcementTimer = Timer(const Duration(milliseconds: 2400), () {
      if (!mounted) return;
      _navigateToChatbot(CiviAccessibilityMode.visuallyChallenged);
    });
  }

  void _navigateToChatbot(CiviAccessibilityMode mode) {
    // Attempt navigation to the Chatbot Interface route
    try {
      Navigator.of(context).pushNamed(
        '/chatbot',
        arguments: {
          'language': _language,
          'mode': mode,
        },
      );
    } catch (_) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: _deepForest,
          content: Text(
            'Mode: ${mode == CiviAccessibilityMode.standard ? "Standard" : "Visually Challenged"}. (Chatbot Interface screen pending)',
            style: const TextStyle(color: _lightGreen),
          ),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  /// Physical BACK button handler: Navigates back to the Language Selection screen.
  /// Preserves the previously selected language.
  void handlePhysicalBackPress() {
    if (_isAnnouncing) return;
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop(_language);
    } else {
      Navigator.of(context).pushReplacementNamed(
        '/language_selection',
        arguments: _language,
      );
    }
  }

  void _handleKeyEvent(KeyEvent event) {
    if (event is KeyDownEvent) {
      if (event.logicalKey == LogicalKeyboardKey.keyM ||
          event.logicalKey == LogicalKeyboardKey.tab) {
        switchAccessibilityMode();
      } else if (event.logicalKey == LogicalKeyboardKey.keyY ||
          event.logicalKey == LogicalKeyboardKey.enter ||
          event.logicalKey == LogicalKeyboardKey.space) {
        confirmMode();
      } else if (event.logicalKey == LogicalKeyboardKey.keyV) {
        activateDedicatedVisuallyChallengedMode();
      } else if (event.logicalKey == LogicalKeyboardKey.keyB ||
          event.logicalKey == LogicalKeyboardKey.escape) {
        handlePhysicalBackPress();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final isDesktop = size.width > 600;
    final horizontalPadding = size.width < 360 ? 16.0 : 24.0;
    final availableWidth = size.width - (horizontalPadding * 2);
    final panelWidth = isDesktop ? 460.0 : (size.width * 0.90).clamp(240.0, availableWidth < 400.0 ? availableWidth : 400.0);
    final isTamil = _language == CiviLanguage.tamil;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) handlePhysicalBackPress();
      },
      child: Scaffold(
        body: KeyboardListener(
        focusNode: _focusNode,
        autofocus: true,
        onKeyEvent: _handleKeyEvent,
        child: AnimatedBuilder(
          animation: _bgController,
          builder: (context, child) {
            return Container(
              width: double.infinity,
              height: double.infinity,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: _topAlignmentAnim.value,
                  end: _bottomAlignmentAnim.value,
                  colors: const [_deepForest, _emerald],
                ),
              ),
              child: child,
            );
          },
          child: SafeArea(
            child: Stack(
              children: [
                Center(
                  child: SingleChildScrollView(
                    padding: EdgeInsets.symmetric(horizontal: horizontalPadding, vertical: 24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                    // Spoken announcement banner (active when dedicated button is pressed)
                    if (_isAnnouncing)
                      Container(
                        width: panelWidth,
                        margin: const EdgeInsets.only(bottom: 24),
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.7),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: _lightGreen, width: 2),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.volume_up, color: _lightGreen, size: 28),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Text(
                                _announcementText ?? '',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),


                    // Screen Question Heading
                    Text(
                      isTamil
                          ? 'CIVI-ஐ நீங்கள் எவ்வாறு பயன்படுத்த விரும்புகிறீர்கள்?'
                          : 'How would you like to use CIVI?',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: _lightGreen,
                        fontSize: size.width < 360 ? 17 : 20,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 32),

                    // Option 1: Standard Mode
                    _buildDynamicIslandPanel(
                      mode: CiviAccessibilityMode.standard,
                      icon: Icons.chat_bubble_outline,
                      title: isTamil ? 'நிலையான பயன்முறை' : 'Standard Mode',
                      subtitle: isTamil
                          ? 'உரை மற்றும் குரல்வழி தொடர்பு.'
                          : 'Text and voice interaction.',
                      width: panelWidth,
                    ),
                    const SizedBox(height: 20),

                    // Option 2: Visually Challenged Mode
                    _buildDynamicIslandPanel(
                      mode: CiviAccessibilityMode.visuallyChallenged,
                      icon: Icons.record_voice_over_outlined,
                      title: isTamil
                          ? 'பார்வைக் குறைபாடு பயன்முறை'
                          : 'Visually Challenged Mode',
                      subtitle: isTamil
                          ? 'குரல்வழி அணுகல் தொடர்பு.'
                          : 'Voice-based accessible interaction.',
                      width: panelWidth,
                    ),

                    const SizedBox(height: 36),

                    // On-screen Confirm Button (mirrors physical YES button)
                    SizedBox(
                      width: panelWidth,
                      height: 54,
                      child: ElevatedButton(
                        onPressed: _isAnnouncing ? null : confirmMode,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: _lightGreen,
                          foregroundColor: _deepForest,
                          elevation: 4,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(27),
                          ),
                        ),
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(Icons.check_circle_outline, size: 22),
                              const SizedBox(width: 10),
                              Text(
                                isTamil ? 'உறுதி செய் (YES)' : 'CONFIRM (YES)',
                                style: const TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: 1.2,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),

                    const SizedBox(height: 16),

                    // Dedicated Visually Challenged button emulator
                    SizedBox(
                      width: panelWidth,
                      child: OutlinedButton.icon(
                        onPressed: _isAnnouncing
                            ? null
                            : activateDedicatedVisuallyChallengedMode,
                        style: OutlinedButton.styleFrom(
                          foregroundColor: _lightGreen,
                          side: const BorderSide(color: _lightGreen, width: 1.5),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(27),
                          ),
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
                        ),
                        icon: const Icon(Icons.accessibility_new, size: 20),
                        label: FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(
                            isTamil
                                ? 'பார்வைக் குறைபாடு நேரடி பொத்தான் (V)'
                                : 'Dedicated Visually Challenged Button (Press V)',
                            style: const TextStyle(
                              fontSize: 13,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),
                    ),

                    const SizedBox(height: 12),

                    // Physical Mode Selector test helper
                    TextButton.icon(
                      onPressed: switchAccessibilityMode,
                      icon: const Icon(Icons.swap_vert, color: Colors.white70, size: 16),
                      label: Text(
                        isTamil
                            ? 'பயன்முறை மாற்றி (M அழுத்தவும்)'
                            : 'Simulate Mode Selector (Press M)',
                        style: const TextStyle(color: Colors.white70, fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            // Top-left back-navigation arrow (matching chatbot UI styling)
            Positioned(
              top: 8,
              left: 8,
              child: IconButton(
                tooltip: isTamil ? 'பின்னால் (Back)' : 'Back',
                icon: const Icon(
                  Icons.arrow_back_ios_new,
                  color: Colors.white,
                  size: 20,
                ),
                onPressed: handlePhysicalBackPress,
              ),
            ),
          ],
        ),
      ),
    ),
  ),
),
);
  }

  Widget _buildDynamicIslandPanel({
    required CiviAccessibilityMode mode,
    required IconData icon,
    required String title,
    required String subtitle,
    required double width,
  }) {
    final bool isSelected = _selectedMode == mode;
    final bool isHovered = _hoveredMode == mode;

    final Color backgroundColor = isSelected
        ? Colors.black.withValues(alpha: 0.55)
        : isHovered
            ? Colors.black.withValues(alpha: 0.40)
            : Colors.black.withValues(alpha: 0.28);

    final Color borderColor = isSelected
        ? _lightGreen
        : isHovered
            ? _lightGreen.withValues(alpha: 0.5)
            : Colors.white.withValues(alpha: 0.18);

    final double borderWidth = isSelected ? 2.5 : 1.2;

    return MouseRegion(
      onEnter: (_) => setState(() => _hoveredMode = mode),
      onExit: (_) => setState(() => _hoveredMode = null),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => selectMode(mode),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          width: width,
          constraints: const BoxConstraints(minHeight: 84),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(42),
            border: Border.all(color: borderColor, width: borderWidth),
            boxShadow: isSelected
                ? [
                    BoxShadow(
                      color: _lightGreen.withValues(alpha: 0.35),
                      blurRadius: 18,
                      spreadRadius: 1,
                      offset: const Offset(0, 4),
                    ),
                  ]
                : [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.2),
                      blurRadius: 8,
                      offset: const Offset(0, 4),
                    ),
                  ],
          ),
          child: Row(
            children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 26,
                height: 26,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: isSelected ? _lightGreen : Colors.transparent,
                  border: Border.all(
                    color: isSelected ? _lightGreen : Colors.white38,
                    width: 2,
                  ),
                ),
                child: isSelected
                    ? const Icon(Icons.check, size: 16, color: _deepForest)
                    : null,
              ),
              const SizedBox(width: 16),
              Icon(icon, color: isSelected ? _lightGreen : Colors.white70, size: 26),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: isSelected ? Colors.white : Colors.white.withValues(alpha: 0.9),
                        fontSize: 17,
                        fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      subtitle,
                      style: TextStyle(
                        color: isSelected ? _lightGreen : Colors.white54,
                        fontSize: 12,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

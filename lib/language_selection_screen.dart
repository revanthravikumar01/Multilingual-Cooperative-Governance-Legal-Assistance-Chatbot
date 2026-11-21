import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';

/// Available languages supported by CIVI.
enum CiviLanguage { english, tamil }

/// Language Selection Screen for CIVI.
///
/// Features:
/// - Deep Forest Green (#124E43) to Emerald Green (#2D8C75) with smooth ambient animation.
/// - Apple Dynamic Island inspired pill-like language panels for English and தமிழ் (Tamil).
/// - Default selection: English.
/// - Switch language function [switchLanguage] ready for physical selector button / ESP32 integration.
/// - Single-press confirmation [confirmLanguage] ready for physical YES button / ESP32 integration.
/// - Hover visual feedback independent of active selection.
/// - Keyboard shortcuts ('L' to toggle language, 'Y' or 'Enter' to confirm) for hardware emulation.
class LanguageSelectionScreen extends StatefulWidget {
  const LanguageSelectionScreen({super.key});

  @override
  State<LanguageSelectionScreen> createState() =>
      _LanguageSelectionScreenState();
}

class _LanguageSelectionScreenState extends State<LanguageSelectionScreen>
    with SingleTickerProviderStateMixin {
  // Theme palette
  static const Color _deepForest = Color(0xFF124E43);
  static const Color _emerald = Color(0xFF2D8C75);
  static const Color _lightGreen = Color(0xFFEAF3EF);

  // Selection state
  CiviLanguage _selectedLanguage = CiviLanguage.english;
  CiviLanguage? _hoveredLanguage;

  // Background ambient animation
  late final AnimationController _bgController;
  late final Animation<Alignment> _topAlignmentAnim;
  late final Animation<Alignment> _bottomAlignmentAnim;

  final FocusNode _focusNode = FocusNode();

  @override
  void initState() {
    super.initState();

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
      _selectedLanguage = args;
    }
  }

  @override
  void dispose() {
    _focusNode.dispose();
    _bgController.dispose();
    super.dispose();
  }

  /// Cycles between English and Tamil (Order: English -> Tamil -> English).
  /// Designed to be triggered directly by the ESP32 physical Language Selector button.
  void switchLanguage() {
    setState(() {
      _selectedLanguage = (_selectedLanguage == CiviLanguage.english)
          ? CiviLanguage.tamil
          : CiviLanguage.english;
    });
  }

  /// Directly selects a specific language (via touch/click).
  void selectLanguage(CiviLanguage lang) {
    if (_selectedLanguage != lang) {
      setState(() {
        _selectedLanguage = lang;
      });
    }
  }

  /// Confirms the selected language on a single press.
  /// Designed to be triggered directly by the ESP32 physical YES button.
  void confirmLanguage() {
    // Navigate to Accessibility Confirmation Screen with the selected language
    try {
      Navigator.of(context).pushNamed(
        '/accessibility_confirmation',
        arguments: _selectedLanguage,
      );
    } catch (_) {
      // Fallback notification when route is not yet implemented
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: _deepForest,
          content: Text(
            'Confirmed: ${_selectedLanguage == CiviLanguage.english ? "English" : "தமிழ்"}. (Accessibility Confirmation Screen pending)',
            style: const TextStyle(color: _lightGreen),
          ),
          duration: const Duration(seconds: 2),
        ),
      );
    }
  }

  void _handleKeyEvent(KeyEvent event) {
    if (event is KeyDownEvent) {
      if (event.logicalKey == LogicalKeyboardKey.keyL ||
          event.logicalKey == LogicalKeyboardKey.tab) {
        switchLanguage();
      } else if (event.logicalKey == LogicalKeyboardKey.keyY ||
          event.logicalKey == LogicalKeyboardKey.enter ||
          event.logicalKey == LogicalKeyboardKey.space) {
        confirmLanguage();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final isDesktop = size.width > 600;
    final horizontalPadding = size.width < 360 ? 16.0 : 24.0;
    final availableWidth = size.width - (horizontalPadding * 2);
    final panelWidth = isDesktop ? 440.0 : (size.width * 0.90).clamp(240.0, availableWidth < 380.0 ? availableWidth : 380.0);

    return Scaffold(
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
            child: Center(
              child: SingleChildScrollView(
                padding: EdgeInsets.symmetric(horizontal: horizontalPadding, vertical: 28),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Screen header
                    const Text(
                      'Select Language / மொழியைத் தேர்ந்தெடுக்கவும்',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: _lightGreen,
                        fontSize: 16,
                        fontWeight: FontWeight.w500,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const SizedBox(height: 36),

                    // Language Panels (Dynamic Island style)
                    _buildDynamicIslandPanel(
                      language: CiviLanguage.english,
                      primaryText: 'English',
                      secondaryText: 'Default Language',
                      width: panelWidth,
                    ),
                    const SizedBox(height: 22),
                    _buildDynamicIslandPanel(
                      language: CiviLanguage.tamil,
                      primaryText: 'தமிழ்',
                      secondaryText: 'Tamil',
                      width: panelWidth,
                    ),

                    const SizedBox(height: 44),

                    // On-screen Confirm Button (mirrors physical YES button)
                    SizedBox(
                      width: panelWidth,
                      height: 54,
                      child: ElevatedButton(
                        onPressed: confirmLanguage,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: _lightGreen,
                          foregroundColor: _deepForest,
                          elevation: 4,
                          shape: RoundedRectangle64(),
                        ),
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const Icon(Icons.check_circle_outline, size: 22),
                              const SizedBox(width: 10),
                              Text(
                                _selectedLanguage == CiviLanguage.english
                                    ? 'CONFIRM (YES)'
                                    : 'உறுதி செய் (YES)',
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

                    const SizedBox(height: 18),

                    // Physical Hardware Emulation helper button
                    TextButton.icon(
                      onPressed: switchLanguage,
                      icon: const Icon(Icons.swap_vert, color: Colors.white70, size: 18),
                      label: const Text(
                        'Simulate Physical Selector (Press L)',
                        style: TextStyle(color: Colors.white70, fontSize: 13),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDynamicIslandPanel({
    required CiviLanguage language,
    required String primaryText,
    required String secondaryText,
    required double width,
  }) {
    final bool isSelected = _selectedLanguage == language;
    final bool isHovered = _hoveredLanguage == language;

    // Dynamic Island styling calculations
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
      onEnter: (_) => setState(() => _hoveredLanguage = language),
      onExit: (_) => setState(() => _hoveredLanguage = null),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTap: () => selectLanguage(language),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          width: width,
          constraints: const BoxConstraints(minHeight: 80),
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
          decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(40), // Pill shape
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
              // Selection indicator pill dot
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                width: 24,
                height: 24,
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
              const SizedBox(width: 20),

              // Language text
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      primaryText,
                      style: TextStyle(
                        color: isSelected ? Colors.white : Colors.white.withValues(alpha: 0.9),
                        fontSize: 20,
                        fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                        letterSpacing: 0.5,
                      ),
                    ),
                    Text(
                      secondaryText,
                      style: TextStyle(
                        color: isSelected ? _lightGreen : Colors.white54,
                        fontSize: 12,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ],
                ),
              ),

              // Subtle selection status badge
              if (isSelected)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: _lightGreen.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Text(
                    'ACTIVE',
                    style: TextStyle(
                      color: _lightGreen,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 1.0,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class RoundedRectangle64 extends RoundedRectangleBorder {
  RoundedRectangle64() : super(borderRadius: BorderRadius.circular(28));
}

import 'dart:async';
import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';
import 'language_selection_screen.dart';
import 'accessibility_confirmation_screen.dart';
import 'services/civi_conversation.dart';

export 'services/civi_conversation.dart' show CiviChatMessage, VoiceHardwareStatus;

/// Main Chatbot Screen for CIVI.
/// Dispatches between Standard Mode and Visually Challenged Mode based on navigation parameters.
class ChatbotScreen extends StatefulWidget {
  final CiviLanguage? language;
  final CiviAccessibilityMode? mode;

  const ChatbotScreen({super.key, this.language, this.mode});

  @override
  State<ChatbotScreen> createState() => _ChatbotScreenState();
}

class _ChatbotScreenState extends State<ChatbotScreen> {
  late CiviLanguage _language;
  late CiviAccessibilityMode _mode;

  @override
  void initState() {
    super.initState();
    _language = widget.language ?? CiviLanguage.english;
    _mode = widget.mode ?? CiviAccessibilityMode.standard;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is Map) {
      if (args['language'] is CiviLanguage) {
        _language = args['language'] as CiviLanguage;
      }
      if (args['mode'] is CiviAccessibilityMode) {
        _mode = args['mode'] as CiviAccessibilityMode;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_mode == CiviAccessibilityMode.visuallyChallenged) {
      return VisuallyChallengedChatbotView(language: _language);
    }
    return StandardChatbotView(language: _language);
  }
}

// =============================================================================
// STANDARD MODE IMPLEMENTATION
// =============================================================================

class StandardChatbotView extends StatefulWidget {
  final CiviLanguage language;

  const StandardChatbotView({super.key, required this.language});

  @override
  State<StandardChatbotView> createState() => _StandardChatbotViewState();
}

class _StandardChatbotViewState extends State<StandardChatbotView>
    with SingleTickerProviderStateMixin {
  // Theme colors - refined to softer, lighter tones
  static const Color _deepForest = Color(0xFF1B5E52);
  static const Color _emerald = Color(0xFF329881);
  static const Color _lightGreen = Color(0xFFEEF6F2);

  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocusNode = FocusNode();

  /// Backend session, messages (typed here or spoken at the kiosk) and voice.
  late final CiviConversation _conversation;
  int _shownMessages = 0;
  bool _isSessionReset = false;

  List<CiviChatMessage> get _messages => _conversation.messages;
  VoiceHardwareStatus get _voiceStatus => _conversation.status;
  int get _recordingSeconds => _conversation.recordingSeconds;
  bool get _isWaitingForAnswer => _conversation.waitingForAnswer;

  late final AnimationController _pulseController;
  late final Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    // Register global hardware keyboard shortcut handler for persistent M, R, C, B responses
    HardwareKeyboard.instance.addHandler(_handleHardwareKeyEvent);

    _conversation = CiviConversation(
      language: widget.language == CiviLanguage.tamil ? 'ta' : 'en',
      speakTypedAnswers: false, // Standard mode: typed questions get text answers (Decision 14)
    )
      ..onNotice = _showNotice
      ..addListener(_onConversationChanged);
    _conversation.start();

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.85, end: 1.15).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_handleHardwareKeyEvent);
    _conversation.removeListener(_onConversationChanged);
    _conversation.dispose();
    _textController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  void _onConversationChanged() {
    if (!mounted) return;
    setState(() {
      if (_messages.isNotEmpty) _isSessionReset = false;
    });
    // New messages (including questions asked at the kiosk) scroll into view.
    if (_messages.length != _shownMessages || _isWaitingForAnswer) {
      _shownMessages = _messages.length;
      _scrollToBottom();
    }
  }

  void _showNotice(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: _deepForest,
        content: Text(message, style: const TextStyle(color: _lightGreen)),
        duration: const Duration(seconds: 3),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // PHYSICAL HARDWARE BUTTON HOOKS (keyboard stands in for the ESP32 buttons)
  // ---------------------------------------------------------------------------

  /// Hook for physical button: MICROPHONE
  /// 1st press: starts recording (stops any answer being spoken).
  /// 2nd press: stops and submits the voice question.
  void handlePhysicalVoiceSelectorPress() {
    _inputFocusNode.unfocus();
    _conversation.micPressed();
  }

  /// Hook for physical button: REPEAT VOICE
  /// Replays the last spoken answer (never the user question).
  void handlePhysicalRepeatVoicePress() => _conversation.repeat();

  /// Hook for physical button: CONFIRM
  /// Speaks the complete latest answer instead of the short summary (Decision 24).
  void handlePhysicalConfirmPress() => _conversation.confirmFullAnswer();

  /// Hook for physical button: BACK
  /// 1st Press: Resets active session and conversation.
  /// 2nd Press (when already reset): Navigates back to Accessibility Confirmation screen.
  void handlePhysicalBackPress() {
    if (!_isSessionReset && _messages.isNotEmpty) {
      handlePhysicalResetPress();
    } else {
      _navigateBackToAccessibility();
    }
  }

  /// Reliably navigates back to the Accessibility Confirmation screen,
  /// passing the current language. Works regardless of navigator stack depth.
  void _navigateBackToAccessibility() {
    Navigator.of(context).pushNamedAndRemoveUntil(
      '/accessibility_confirmation',
      (route) => route.settings.name == '/language_selection' || route.isFirst,
      arguments: widget.language,
    );
  }

  /// Hook for Session Reset: ends the backend session and starts a new one.
  void handlePhysicalResetPress() {
    _inputFocusNode.unfocus();
    _textController.clear();
    _conversation.reset();
    setState(() {
      _isSessionReset = true;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: _deepForest,
        content: Text(
          widget.language == CiviLanguage.tamil
              ? 'அமர்வு மீட்டமைக்கப்பட்டது. புதிய உரையாடலைத் தொடங்கலாம்.'
              : 'Session reset. Conversation history cleared.',
          style: const TextStyle(color: _lightGreen),
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  Future<void> _handleSendTypedMessage() async {
    final text = _textController.text.trim();
    // One question at a time, so answers can't arrive out of order.
    if (text.isEmpty || _isWaitingForAnswer) return;
    _textController.clear();
    // Unfocus text input so keyboard shortcuts (M, R, C, B) become active immediately
    _inputFocusNode.unfocus();
    await _conversation.sendText(text);
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  bool _handleHardwareKeyEvent(KeyEvent event) {
    if (!mounted) return false;

    // Only process keyboard shortcuts when this route is the active (top) route
    final modalRoute = ModalRoute.of(context);
    if (modalRoute != null && !modalRoute.isCurrent) return false;

    if (event is! KeyDownEvent) return false;

    // Do not trigger shortcuts while the user is actively typing in the text input field
    if (_inputFocusNode.hasFocus) return false;

    if (event.logicalKey == LogicalKeyboardKey.keyM ||
        event.logicalKey == LogicalKeyboardKey.keyV) {
      handlePhysicalVoiceSelectorPress();
      return true;
    } else if (event.logicalKey == LogicalKeyboardKey.keyR) {
      // Do not interrupt an active recording unexpectedly
      if (_voiceStatus != VoiceHardwareStatus.recording) {
        handlePhysicalRepeatVoicePress();
        return true;
      }
    } else if (event.logicalKey == LogicalKeyboardKey.keyC) {
      handlePhysicalConfirmPress();
      return true;
    } else if (event.logicalKey == LogicalKeyboardKey.escape ||
        event.logicalKey == LogicalKeyboardKey.keyB) {
      handlePhysicalBackPress();
      return true;
    }

    return false;
  }

  @override
  Widget build(BuildContext context) {
    final isTamil = widget.language == CiviLanguage.tamil;
    final mediaQuery = MediaQuery.of(context);
    final isLandscape = mediaQuery.orientation == Orientation.landscape;
    final isCompactHeight = isLandscape && mediaQuery.size.height < 500;

    return PopScope(
      // Intercept Android system back button / back gesture.
      // canPop: false means we handle it ourselves.
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) handlePhysicalBackPress();
      },
      child: Scaffold(
        backgroundColor: const Color(0xFFF7FAF8),
        body: SafeArea(
          child: GestureDetector(
            behavior: HitTestBehavior.translucent,
            onTap: () {
              if (_inputFocusNode.hasFocus) {
                _inputFocusNode.unfocus();
              }
            },
            child: Stack(
              children: [
                Column(
                  children: [
                    // 1. Header with branding, mode indicator, and reset button
                    _buildHeader(isTamil, isCompactHeight: isCompactHeight),

                    // 2. Legal Disclaimer banner
                    _buildLegalDisclaimer(isTamil, isCompactHeight: isCompactHeight),

                    // 3. Conversation Message Area
                    Expanded(
                      child: _messages.isEmpty
                          ? _buildEmptyState(isTamil, isCompactHeight: isCompactHeight)
                          : ListView.builder(
                              controller: _scrollController,
                              padding: EdgeInsets.symmetric(horizontal: 16, vertical: isCompactHeight ? 6 : 12),
                              // One extra row for the "CIVI is working" bubble while waiting for an answer.
                              itemCount: _messages.length + (_isWaitingForAnswer ? 1 : 0),
                              itemBuilder: (context, index) {
                                if (index == _messages.length) {
                                  return CiviThinkingBubble(isTamil: isTamil);
                                }
                                return _buildMessageItem(_messages[index], isCompactHeight: isCompactHeight);
                              },
                            ),
                    ),

                    // 4. Hardware Voice Status Indicator
                    _buildVoiceStatusBar(isTamil, isCompactHeight: isCompactHeight),

                    // 5. Text Input Area (with on-screen microphone button)
                    _buildTextInputArea(isTamil, isCompactHeight: isCompactHeight),
                  ],
                ),

                // Centered animated listening visual during voice recording
                if (_voiceStatus == VoiceHardwareStatus.recording)
                  CiviListeningVisual(
                    isTamil: isTamil,
                    seconds: _recordingSeconds,
                    onTap: handlePhysicalVoiceSelectorPress,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(bool isTamil, {bool isCompactHeight = false}) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: 8,
        vertical: isCompactHeight ? 4 : 8,
      ),
      decoration: const BoxDecoration(
        color: _deepForest,
        boxShadow: [
          BoxShadow(
            color: Colors.black12,
            blurRadius: 4,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          // On-screen Back Button (same logic as physical BACK)
          IconButton(
            tooltip: isTamil ? 'பின்னால் (Back)' : 'Back',
            padding: isCompactHeight ? EdgeInsets.zero : const EdgeInsets.all(8),
            constraints: isCompactHeight ? const BoxConstraints(minWidth: 36, minHeight: 36) : null,
            icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 20),
            onPressed: handlePhysicalBackPress,
          ),

          // CIVI Brand Logo - noticeably enlarged in portrait, gracefully scaled in landscape mobile
          Image.asset(
            'assets/images/civi_logo.png',
            height: isCompactHeight ? 34 : 48,
            fit: BoxFit.contain,
            errorBuilder: (context, error, stackTrace) {
              return Text(
                'CIVI',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                  fontSize: isCompactHeight ? 18 : 22,
                  letterSpacing: 2.0,
                ),
              );
            },
          ),
          const SizedBox(width: 10),

          // Title and status badges
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  isTamil ? 'சட்ட & கூட்டுறவு உதவி' : 'Legal & Governance Kiosk',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                    fontSize: isCompactHeight ? 13 : 14,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                SizedBox(height: isCompactHeight ? 1 : 2),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      padding: EdgeInsets.symmetric(horizontal: 6, vertical: isCompactHeight ? 1 : 2),
                      decoration: BoxDecoration(
                        color: _emerald,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        isTamil ? 'நிலையான பயன்முறை' : 'Standard Mode',
                        style: TextStyle(color: Colors.white, fontSize: isCompactHeight ? 9 : 10),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        isTamil ? 'தமிழ்' : 'English',
                        style: TextStyle(color: _lightGreen.withValues(alpha: 0.8), fontSize: isCompactHeight ? 10 : 11),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),

          // Session Reset Button
          IconButton(
            tooltip: isTamil ? 'அமர்வு மீட்டமை (Reset)' : 'Reset Session',
            padding: isCompactHeight ? EdgeInsets.zero : const EdgeInsets.all(8),
            constraints: isCompactHeight ? const BoxConstraints(minWidth: 36, minHeight: 36) : null,
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: handlePhysicalResetPress,
          ),
        ],
      ),
    );
  }

  Widget _buildLegalDisclaimer(bool isTamil, {bool isCompactHeight = false}) {
    return Container(
      width: double.infinity,
      color: const Color(0xFFFFF9E6),
      padding: EdgeInsets.symmetric(
        horizontal: 14,
        vertical: isCompactHeight ? 4 : 8,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.gavel, size: isCompactHeight ? 14 : 16, color: const Color(0xFF8A6D3B)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isTamil
                  ? 'தகவல் அறிவிப்பு: CIVI கூட்டுறவு சட்டம் பற்றிய வழிகாட்டுதலை மட்டுமே வழங்குகிறது; இது சான்றளிக்கப்பட்ட வழக்கறிஞர் ஆலோசனை அல்ல.'
                  : 'Notice: CIVI provides informational legal guidance on cooperative governance, not certified legal counsel. Verify with official statutory gazettes.',
              style: TextStyle(
                fontSize: isCompactHeight ? 10 : 11,
                color: const Color(0xFF8A6D3B),
                height: isCompactHeight ? 1.2 : 1.3,
              ),
              maxLines: isCompactHeight ? 2 : null,
              overflow: isCompactHeight ? TextOverflow.ellipsis : TextOverflow.clip,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState(bool isTamil, {bool isCompactHeight = false}) {
    return Center(
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        padding: EdgeInsets.symmetric(
          horizontal: 24.0,
          vertical: isCompactHeight ? 8.0 : 24.0,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.chat_bubble_outline,
              size: isCompactHeight ? 32 : 48,
              color: _emerald.withValues(alpha: 0.4),
            ),
            SizedBox(height: isCompactHeight ? 6 : 12),
            Text(
              _isSessionReset
                  ? (isTamil
                      ? 'உரையாடல் மீட்டமைக்கப்பட்டது.\nகீழே தட்டச்சு செய்யவும் அல்லது கேள்வி கேட்க ஒலிவாங்கி (Mic) பொத்தானை அழுத்தவும்.'
                      : 'Session is clear.\nType your question below or press the Mic button to speak.')
                  : (isTamil
                      ? 'வணக்கம்! கூட்டுறவுச் சங்கங்கள் பற்றிக் கேளுங்கள்: பதிவு, உறுப்பினர், தேர்தல், கூட்டங்கள், தணிக்கை, நிர்வாகம்.\n'
                          'பதில்கள் சட்ட ஆவணங்களிலிருந்து மட்டுமே, மூலங்களுடன் வழங்கப்படும்.\n\n'
                          'கீழே தட்டச்சு செய்யவும் அல்லது ஒலிவாங்கி (Mic) பொத்தானை அழுத்திப் பேசவும்.'
                      : 'Welcome! Ask about co-operative societies: registration, membership, elections, meetings, '
                          'audit or management.\nAnswers come only from the official legal documents, with sources.\n\n'
                          'Type your question below or press the Mic button to speak.'),
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.black.withValues(alpha: 0.5),
                fontSize: isCompactHeight ? 11.5 : 13,
                height: isCompactHeight ? 1.3 : 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMessageItem(CiviChatMessage msg, {bool isCompactHeight = false}) {
    final screenWidth = MediaQuery.of(context).size.width;
    final isCompact = screenWidth < 400;

    if (msg.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          constraints: BoxConstraints(maxWidth: screenWidth * 0.84),
          margin: EdgeInsets.only(left: isCompact ? 20 : 40, bottom: isCompactHeight ? 6 : 10),
          padding: EdgeInsets.symmetric(horizontal: 16, vertical: isCompactHeight ? 8 : 12),
          decoration: BoxDecoration(
            color: _deepForest,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(16),
              topRight: Radius.circular(4),
              bottomLeft: Radius.circular(16),
              bottomRight: Radius.circular(16),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (msg.isVoice)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4.0),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.mic, size: 13, color: _lightGreen.withValues(alpha: 0.8)),
                      const SizedBox(width: 4),
                      Text(
                        'Voice Query',
                        style: TextStyle(
                          fontSize: 10,
                          color: _lightGreen.withValues(alpha: 0.8),
                        ),
                      ),
                    ],
                  ),
                ),
              Text(
                msg.text,
                style: TextStyle(color: Colors.white, fontSize: isCompactHeight ? 13 : 14, height: 1.35),
              ),
            ],
          ),
        ),
      );
    }

    // CIVI response message bubble
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: screenWidth * 0.88),
        margin: EdgeInsets.only(right: isCompact ? 18 : 32, bottom: isCompactHeight ? 8 : 12),
        padding: EdgeInsets.all(isCompactHeight ? 11 : 15),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(4),
            topRight: Radius.circular(16),
            bottomLeft: Radius.circular(16),
            bottomRight: Radius.circular(16),
          ),
          border: Border.all(color: Colors.black.withValues(alpha: 0.08)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.04),
              blurRadius: 6,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: _deepForest,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: const Text(
                    'CIVI',
                    style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                  ),
                ),
                const SizedBox(width: 8),
                Flexible(
                  child: Text(
                    'Cooperative Legal Guidance',
                    style: TextStyle(
                      fontSize: 11,
                      color: Colors.black.withValues(alpha: 0.5),
                      fontWeight: FontWeight.w500,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              msg.text,
              style: const TextStyle(
                color: Color(0xFF1E2D2B),
                fontSize: 13.5,
                height: 1.45,
              ),
            ),
            // Sources built by the backend from document metadata (Decision 10), shown ONLY if available.
            if (msg.citations.isNotEmpty || msg.sourceReference != null) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: _lightGreen.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: _emerald.withValues(alpha: 0.3)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final label in (msg.citations.isNotEmpty ? msg.citations : [msg.sourceReference!]))
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Padding(
                              padding: EdgeInsets.only(top: 1),
                              child: Icon(Icons.menu_book, size: 14, color: _deepForest),
                            ),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                label,
                                style: const TextStyle(
                                  fontSize: 11,
                                  color: _deepForest,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildVoiceStatusBar(bool isTamil, {bool isCompactHeight = false}) {
    Color barColor = _deepForest;
    IconData icon = Icons.radio_button_checked;
    String statusMessage = '';

    switch (_voiceStatus) {
      case VoiceHardwareStatus.idle:
        barColor = _deepForest;
        icon = Icons.radio_button_checked;
        statusMessage = isTamil
            ? 'கேள்வி கேட்க ஒலிவாங்கி (Mic) பொத்தானை அழுத்தவும்.'
            : 'Press the Mic button to speak.';
        break;
      case VoiceHardwareStatus.recording:
        barColor = const Color(0xFFB71C1C);
        icon = Icons.mic;
        statusMessage = isTamil
            ? 'பதிவாகிறது (${_recordingSeconds}s)... சமர்ப்பிக்க மீண்டும் ஒலிவாங்கி (Mic) பொத்தானை அழுத்தவும்.'
            : 'Recording (${_recordingSeconds}s)... Press the Mic button again to submit.';
        break;
      case VoiceHardwareStatus.processing:
        barColor = _emerald;
        icon = Icons.hourglass_top;
        statusMessage = isTamil
            ? 'சட்டக் கேள்வி ஆய்வு செய்யப்படுகிறது...'
            : 'Processing voice legal inquiry...';
        break;
      case VoiceHardwareStatus.speaking:
        barColor = const Color(0xFF1565C0);
        icon = Icons.record_voice_over;
        statusMessage = isTamil
            ? 'CIVI பதிலை குரல்வழியாகக் கூறுகிறது...'
            : 'CIVI is speaking the answer...';
        break;
      case VoiceHardwareStatus.replaying:
        barColor = const Color(0xFF338A40);
        icon = Icons.replay;
        statusMessage = isTamil
            ? 'மீண்டும் ஒலி (Repeat Voice)...'
            : 'Replaying latest CIVI answer (Repeat Voice)...';
        break;
    }

    return InkWell(
      onTap: handlePhysicalVoiceSelectorPress,
      child: Container(
        width: double.infinity,
        color: barColor,
        padding: EdgeInsets.symmetric(
          horizontal: 16,
          vertical: isCompactHeight ? 4 : 8,
        ),
        child: Row(
          children: [
            if (_voiceStatus == VoiceHardwareStatus.recording)
              ScaleTransition(
                scale: _pulseAnimation,
                child: Icon(Icons.fiber_manual_record, color: Colors.white, size: isCompactHeight ? 14 : 16),
              )
            else
              Icon(icon, color: Colors.white, size: isCompactHeight ? 14 : 16),
            SizedBox(width: isCompactHeight ? 8 : 10),
            Expanded(
              child: Text(
                statusMessage,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: isCompactHeight ? 11.5 : 12,
                  fontWeight: FontWeight.w500,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTextInputArea(bool isTamil, {bool isCompactHeight = false}) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: 12,
        vertical: isCompactHeight ? 4 : 8,
      ),
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.06),
            blurRadius: 6,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Row(
        children: [
          // On-Screen Microphone Button (Click to start / stop recording, synchronized with ESP32 button)
          InkWell(
            onTap: handlePhysicalVoiceSelectorPress,
            borderRadius: BorderRadius.circular(20),
            child: Container(
              width: isCompactHeight ? 32 : 38,
              height: isCompactHeight ? 32 : 38,
              margin: const EdgeInsets.only(right: 8),
              decoration: BoxDecoration(
                color: _voiceStatus == VoiceHardwareStatus.recording
                    ? const Color(0xFFB71C1C)
                    : _deepForest.withValues(alpha: 0.09),
                shape: BoxShape.circle,
                border: Border.all(
                  color: _voiceStatus == VoiceHardwareStatus.recording
                      ? Colors.red
                      : _emerald.withValues(alpha: 0.35),
                  width: 1.5,
                ),
              ),
              child: Tooltip(
                message: isTamil
                    ? (_voiceStatus == VoiceHardwareStatus.recording
                        ? 'சமர்ப்பிக்க கிளிக் செய்யவும்'
                        : 'பேச கிளிக் செய்யவும் (ஒலிவாங்கி)')
                    : (_voiceStatus == VoiceHardwareStatus.recording
                        ? 'Click to stop & submit'
                        : 'Click to speak (Mic)'),
                child: Icon(
                  _voiceStatus == VoiceHardwareStatus.recording ? Icons.mic : Icons.mic_none,
                  size: isCompactHeight ? 17 : 20,
                  color: _voiceStatus == VoiceHardwareStatus.recording
                      ? Colors.white
                      : _deepForest,
                ),
              ),
            ),
          ),

          // Rounded Text Input Field
          Expanded(
            child: TextField(
              controller: _textController,
              focusNode: _inputFocusNode,
              onSubmitted: (_) => _handleSendTypedMessage(),
              style: TextStyle(fontSize: isCompactHeight ? 12.5 : 13),
              decoration: InputDecoration(
                hintText: isTamil
                    ? 'சட்டக் கேள்வியை இங்கே தட்டச்சு செய்யவும்...'
                    : 'Type your legal question here...',
                hintStyle: TextStyle(
                  color: Colors.black.withValues(alpha: 0.4),
                  fontSize: isCompactHeight ? 11.5 : 13,
                ),
                contentPadding: EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: isCompactHeight ? 6 : 12,
                ),
                filled: true,
                fillColor: const Color(0xFFF1F5F4),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),

          // On-screen Send Button (No microphone or recording button allowed)
          SizedBox(
            width: isCompactHeight ? 34 : 44,
            height: isCompactHeight ? 34 : 44,
            child: ElevatedButton(
              // Disabled while an answer is on its way (one question at a time).
              onPressed: _isWaitingForAnswer ? null : _handleSendTypedMessage,
              style: ElevatedButton.styleFrom(
                backgroundColor: _deepForest,
                foregroundColor: Colors.white,
                disabledBackgroundColor: _deepForest.withValues(alpha: 0.55),
                padding: EdgeInsets.zero,
                shape: const CircleBorder(),
                elevation: 2,
              ),
              child: _isWaitingForAnswer
                  ? SizedBox(
                      width: isCompactHeight ? 14 : 18,
                      height: isCompactHeight ? 14 : 18,
                      child: const CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : Icon(Icons.send, size: isCompactHeight ? 15 : 18),
            ),
          ),
        ],
      ),
    );
  }
}

/// Shown at the bottom of the chat while the backend searches the law and Gemini writes the answer.
/// Bouncing dots show the app is alive; after a few seconds a counter shows it is still working.
class CiviThinkingBubble extends StatefulWidget {
  const CiviThinkingBubble({super.key, required this.isTamil});

  final bool isTamil;

  @override
  State<CiviThinkingBubble> createState() => _CiviThinkingBubbleState();
}

class _CiviThinkingBubbleState extends State<CiviThinkingBubble> with SingleTickerProviderStateMixin {
  static const Color _deepForest = Color(0xFF1B5E52);
  static const Color _emerald = Color(0xFF329881);

  late final AnimationController _dots;
  late final Timer _clock;
  int _seconds = 0;

  @override
  void initState() {
    super.initState();
    _dots = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat();
    _clock = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _seconds++);
    });
  }

  @override
  void dispose() {
    _clock.cancel();
    _dots.dispose();
    super.dispose();
  }

  String get _message {
    final tamil = widget.isTamil;
    if (_seconds < 4) {
      return tamil ? 'சட்ட ஆவணங்களில் தேடுகிறது' : 'Searching the law documents';
    }
    if (_seconds < 25) {
      return tamil ? 'பதிலைத் தயாரிக்கிறது' : 'Preparing your answer';
    }
    return tamil ? 'இன்னும் வேலை செய்கிறது, சிறிது பொறுக்கவும்' : 'Still working, please wait';
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      label: _message,
      child: Align(
        alignment: Alignment.centerLeft,
        child: Container(
          margin: const EdgeInsets.only(bottom: 12, right: 32),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(4),
              topRight: Radius.circular(16),
              bottomLeft: Radius.circular(16),
              bottomRight: Radius.circular(16),
            ),
            border: Border.all(color: Colors.black.withValues(alpha: 0.08)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              AnimatedBuilder(
                animation: _dots,
                builder: (context, _) => Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [for (var i = 0; i < 3; i++) _dot(i)],
                ),
              ),
              const SizedBox(width: 10),
              Flexible(
                child: Text(
                  _seconds >= 4 ? '$_message… ${_seconds}s' : '$_message…',
                  style: const TextStyle(fontSize: 12.5, color: _deepForest, fontWeight: FontWeight.w500),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _dot(int index) {
    // Each dot rises and falls a little after the previous one.
    final phase = (_dots.value - index * 0.18) % 1.0;
    final lift = phase < 0.5 ? phase * 2 : (1 - phase) * 2;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 2),
      child: Transform.translate(
        offset: Offset(0, -4 * lift),
        child: Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            color: Color.lerp(_emerald.withValues(alpha: 0.45), _deepForest, lift),
            shape: BoxShape.circle,
          ),
        ),
      ),
    );
  }
}

// =============================================================================
// VISUALLY CHALLENGED MODE IMPLEMENTATION
// =============================================================================

class VisuallyChallengedChatbotView extends StatefulWidget {
  final CiviLanguage language;

  const VisuallyChallengedChatbotView({super.key, required this.language});

  @override
  State<VisuallyChallengedChatbotView> createState() =>
      _VisuallyChallengedChatbotViewState();
}

class _VisuallyChallengedChatbotViewState
    extends State<VisuallyChallengedChatbotView>
    with SingleTickerProviderStateMixin {
  // Theme colors - refined to softer, lighter tones
  static const Color _deepForest = Color(0xFF1D5A4E);
  static const Color _emerald = Color(0xFF329881);
  static const Color _lightGreen = Color(0xFFEEF6F2);

  final ScrollController _scrollController = ScrollController();

  /// Backend session, messages (spoken here or at the kiosk) and voice. Every answer is spoken.
  late final CiviConversation _conversation;
  int _shownMessages = 0;

  /// A fixed welcome hint shown first (not legal content), followed by the real conversation.
  List<CiviChatMessage> get _messages => [_welcomeMessage(), ..._conversation.messages];
  VoiceHardwareStatus get _voiceStatus => _conversation.status;
  int get _recordingSeconds => _conversation.recordingSeconds;

  late final AnimationController _pulseController;
  late final Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    // Register global hardware keyboard shortcut handler for persistent M, R, C, B responses
    HardwareKeyboard.instance.addHandler(_handleHardwareKeyEvent);

    _conversation = CiviConversation(
      language: widget.language == CiviLanguage.tamil ? 'ta' : 'en',
      speakTypedAnswers: true, // Visually challenged mode: every answer is spoken (Decision 14)
    )
      ..onNotice = _showNotice
      ..addListener(_onConversationChanged);
    _conversation.start();

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.9, end: 1.1).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  CiviChatMessage _welcomeMessage() {
    final isTamil = widget.language == CiviLanguage.tamil;
    return CiviChatMessage(
      text: isTamil
          ? 'வணக்கம்! CIVI குரல்வழியாக உதவ தயாராக உள்ளது.\n\nகேள்வி கேட்க: பேசத் தொடங்குங்கள் (Start Speaking) – ஒலிவாங்கி (Mic) பொத்தானை அல்லது "M" விசையை அழுத்தவும்.'
          : 'Welcome! CIVI Voice Assistant is ready.\n\nTo ask a question: Start Speaking – Press the Mic button or the "M" key to speak.',
      isUser: false,
      isVoice: true,
      timestamp: DateTime.now(),
    );
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_handleHardwareKeyEvent);
    _conversation.removeListener(_onConversationChanged);
    _conversation.dispose();
    _scrollController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  void _onConversationChanged() {
    if (!mounted) return;
    setState(() {});
    if (_conversation.messages.length != _shownMessages) {
      _shownMessages = _conversation.messages.length;
      _scrollToBottom();
    }
  }

  void _showNotice(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: _deepForest,
        content: Text(message, style: const TextStyle(color: _lightGreen)),
        duration: const Duration(seconds: 3),
      ),
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  // ---------------------------------------------------------------------------
  // PHYSICAL HARDWARE BUTTON HOOKS (keyboard stands in for the ESP32 buttons)
  // ---------------------------------------------------------------------------

  /// Hook for physical button: MICROPHONE (first press records, second press sends)
  void handlePhysicalVoiceSelectorPress() => _conversation.micPressed();

  /// Hook for physical button: REPEAT VOICE
  /// Replays the last spoken answer (never the user question).
  void handlePhysicalRepeatVoicePress() => _conversation.repeat();

  /// Hook for physical button: CONFIRM — speaks the complete answer (Decision 24).
  void handlePhysicalConfirmPress() => _conversation.confirmFullAnswer();

  /// Hook for physical button: BACK
  /// Returns to the Accessibility Confirmation screen reliably.
  void handlePhysicalBackPress() {
    Navigator.of(context).pushNamedAndRemoveUntil(
      '/accessibility_confirmation',
      (route) => route.settings.name == '/language_selection' || route.isFirst,
      arguments: widget.language,
    );
  }

  /// Hook for Session Reset.
  void handlePhysicalResetPress() {
    _conversation.reset();

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        backgroundColor: _deepForest,
        content: Text(
          widget.language == CiviLanguage.tamil
              ? 'அமர்வு மீட்டமைக்கப்பட்டது (Session Reset).'
              : 'Session reset.',
          style: const TextStyle(color: _lightGreen),
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  bool _handleHardwareKeyEvent(KeyEvent event) {
    if (!mounted) return false;

    // Only process keyboard shortcuts when this route is the active (top) route
    final modalRoute = ModalRoute.of(context);
    if (modalRoute != null && !modalRoute.isCurrent) return false;

    if (event is! KeyDownEvent) return false;

    if (event.logicalKey == LogicalKeyboardKey.keyM ||
        event.logicalKey == LogicalKeyboardKey.keyV) {
      handlePhysicalVoiceSelectorPress();
      return true;
    } else if (event.logicalKey == LogicalKeyboardKey.keyR) {
      // Do not interrupt an active recording unexpectedly
      if (_voiceStatus != VoiceHardwareStatus.recording) {
        handlePhysicalRepeatVoicePress();
        return true;
      }
    } else if (event.logicalKey == LogicalKeyboardKey.keyC) {
      handlePhysicalConfirmPress();
      return true;
    } else if (event.logicalKey == LogicalKeyboardKey.escape ||
        event.logicalKey == LogicalKeyboardKey.keyB) {
      handlePhysicalBackPress();
      return true;
    }

    return false;
  }

  @override
  Widget build(BuildContext context) {
    final isTamil = widget.language == CiviLanguage.tamil;
    final mediaQuery = MediaQuery.of(context);
    final isLandscape = mediaQuery.orientation == Orientation.landscape;
    final isCompactHeight = isLandscape && mediaQuery.size.height < 500;

    return PopScope(
      // Intercept Android system back button / back gesture.
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) handlePhysicalBackPress();
      },
      child: Scaffold(
        backgroundColor: const Color(0xFF102420), // Softer, lighter deep forest background
        body: SafeArea(
          child: Stack(
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // 1. Top Header: Visually Challenged Mode & Status
                  _buildAccessibleHeader(isTamil, isCompactHeight: isCompactHeight),

                  // 2. Conversation Area (Natural conversational chat bubbles)
                  Expanded(
                    child: ListView.builder(
                      controller: _scrollController,
                      padding: EdgeInsets.symmetric(horizontal: 18, vertical: isCompactHeight ? 6 : 14),
                      itemCount: _messages.length,
                      itemBuilder: (context, index) {
                        return _buildAccessibleMessageBubble(_messages[index], isCompactHeight: isCompactHeight);
                      },
                    ),
                  ),

                  // 3. Hardware Voice Status Bar
                  _buildAccessibleVoiceStatusBar(isTamil, isCompactHeight: isCompactHeight),

                  // 4. Hardware Reference Guidance Cards (No text input in this mode)
                  _buildAccessibleHardwareCards(isTamil, isCompactHeight: isCompactHeight),
                ],
              ),

              // Centered animated listening visual during voice recording
              if (_voiceStatus == VoiceHardwareStatus.recording)
                CiviListeningVisual(
                  isTamil: isTamil,
                  seconds: _recordingSeconds,
                  onTap: handlePhysicalVoiceSelectorPress,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAccessibleHeader(bool isTamil, {bool isCompactHeight = false}) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: 8,
        vertical: isCompactHeight ? 4 : 8,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFF16322C),
        border: Border(
          bottom: BorderSide(color: _lightGreen.withValues(alpha: 0.35), width: 1.5),
        ),
      ),
      child: Row(
        children: [
          // On-screen Back Button (same logic as physical BACK)
          IconButton(
            tooltip: isTamil ? 'பின்னால் (Back)' : 'Back',
            padding: isCompactHeight ? EdgeInsets.zero : const EdgeInsets.all(8),
            constraints: isCompactHeight ? const BoxConstraints(minWidth: 36, minHeight: 36) : null,
            icon: Icon(Icons.arrow_back_ios_new, color: _lightGreen, size: 20),
            onPressed: handlePhysicalBackPress,
          ),

          // CIVI Brand Logo in accessible top-left header - noticeably enlarged in portrait, scaled in landscape mobile
          Image.asset(
            'assets/images/civi_logo.png',
            height: isCompactHeight ? 34 : 48,
            fit: BoxFit.contain,
            errorBuilder: (context, error, stackTrace) {
              return Text(
                'CIVI',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                  fontSize: isCompactHeight ? 18 : 22,
                  letterSpacing: 1.5,
                ),
              );
            },
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  isTamil ? 'பார்வைக் குறைபாடு பயன்முறை (Visually Challenged Mode)' : 'VISUALLY CHALLENGED MODE',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: isCompactHeight ? 12.5 : 14,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.6,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  isTamil ? 'குரல்வழி சட்ட உதவி (Voice Legal Assistance)' : 'Voice-First Legal Assistance',
                  style: TextStyle(
                    color: _lightGreen.withValues(alpha: 0.85),
                    fontSize: isCompactHeight ? 9.5 : 11,
                    fontWeight: FontWeight.w500,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: isTamil ? 'அமர்வு மீட்டமை (Reset Session)' : 'Reset Session',
            padding: isCompactHeight ? EdgeInsets.zero : const EdgeInsets.all(8),
            constraints: isCompactHeight ? const BoxConstraints(minWidth: 36, minHeight: 36) : null,
            icon: Icon(Icons.refresh, color: Colors.white, size: isCompactHeight ? 20 : 24),
            onPressed: handlePhysicalResetPress,
          ),
        ],
      ),
    );
  }

  /// Builds natural conversational chat bubbles with large readable typography.
  /// Does not explicitly label messages as "Question", "Answer", "User Question" or "Bot Answer".
  Widget _buildAccessibleMessageBubble(CiviChatMessage msg, {bool isCompactHeight = false}) {
    if (msg.isUser) {
      // User chat bubble (speech-to-text converted question)
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: EdgeInsets.only(left: 36, bottom: isCompactHeight ? 8 : 14),
          padding: EdgeInsets.symmetric(horizontal: 18, vertical: isCompactHeight ? 8 : 14),
          decoration: BoxDecoration(
            color: _deepForest,
            borderRadius: const BorderRadius.only(
              topLeft: Radius.circular(20),
              topRight: Radius.circular(6),
              bottomLeft: Radius.circular(20),
              bottomRight: Radius.circular(20),
            ),
            border: Border.all(color: _lightGreen.withValues(alpha: 0.8), width: 2),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.35),
                blurRadius: 8,
                offset: const Offset(0, 3),
              ),
            ],
          ),
          child: Text(
            msg.text,
            style: TextStyle(
              color: Colors.white,
              fontSize: isCompactHeight ? 15 : 18,
              fontWeight: FontWeight.w600,
              height: 1.4,
            ),
          ),
        ),
      );
    }

    // CIVI Chatbot response bubble
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: EdgeInsets.only(right: 30, bottom: isCompactHeight ? 8 : 16),
        padding: EdgeInsets.all(isCompactHeight ? 12 : 18),
        decoration: BoxDecoration(
          color: const Color(0xFF1B3D35),
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(6),
            topRight: Radius.circular(20),
            bottomLeft: Radius.circular(20),
            bottomRight: Radius.circular(20),
          ),
          border: Border.all(color: _lightGreen.withValues(alpha: 0.7), width: 2),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.35),
              blurRadius: 8,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: _deepForest,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: _lightGreen.withValues(alpha: 0.6)),
                  ),
                  child: const Text(
                    'CIVI',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.0,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(Icons.record_voice_over, color: _lightGreen, size: 16),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              msg.text,
              style: TextStyle(
                color: Colors.white,
                fontSize: isCompactHeight ? 15 : 18,
                fontWeight: FontWeight.w500,
                height: 1.45,
              ),
            ),
            // Sources built by the backend from document metadata (Decision 10), shown ONLY if available.
            if (msg.citations.isNotEmpty || msg.sourceReference != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.4),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: _lightGreen.withValues(alpha: 0.4)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final label in (msg.citations.isNotEmpty ? msg.citations : [msg.sourceReference!]))
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 2),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Padding(
                              padding: EdgeInsets.only(top: 1),
                              child: Icon(Icons.menu_book, size: 15, color: _lightGreen),
                            ),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                label,
                                style: const TextStyle(
                                  fontSize: 13,
                                  color: _lightGreen,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildAccessibleVoiceStatusBar(bool isTamil, {bool isCompactHeight = false}) {
    Color barColor = _deepForest;
    IconData icon = Icons.hearing;
    String statusMessage = '';

    switch (_voiceStatus) {
      case VoiceHardwareStatus.idle:
        barColor = const Color(0xFF1B3D35);
        icon = Icons.mic_none;
        statusMessage = isTamil
            ? 'பேசத் தொடங்குங்கள் (Start Speaking) – ஒலிவாங்கி (Mic) அழுத்தவும்.'
            : 'Press the Mic button to speak.';
        break;
      case VoiceHardwareStatus.recording:
        barColor = const Color(0xFF9E1B1B);
        icon = Icons.mic;
        statusMessage = isTamil
            ? 'பதிவாகிறது (Recording) (${_recordingSeconds}s)... சமர்ப்பிக்க மீண்டும் அழுத்தவும்.'
            : 'Recording (${_recordingSeconds}s)... Press the Mic button again to submit.';
        break;
      case VoiceHardwareStatus.processing:
        barColor = _emerald;
        icon = Icons.hourglass_top;
        statusMessage = isTamil
            ? 'ஆய்வு செய்யப்படுகிறது (Processing)...'
            : 'Processing voice legal inquiry...';
        break;
      case VoiceHardwareStatus.speaking:
        barColor = const Color(0xFF15549A);
        icon = Icons.record_voice_over;
        statusMessage = isTamil
            ? 'பதில் கூறப்படுகிறது (Speaking)...'
            : 'CIVI is speaking the answer...';
        break;
      case VoiceHardwareStatus.replaying:
        barColor = const Color(0xFF2E7D32);
        icon = Icons.replay;
        statusMessage = isTamil
            ? 'மீண்டும் ஒலி (Repeat Voice)...'
            : 'Replaying latest CIVI answer (Repeat Voice)...';
        break;
    }

    return InkWell(
      onTap: handlePhysicalVoiceSelectorPress,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: 16,
          vertical: isCompactHeight ? 5 : 10,
        ),
        decoration: BoxDecoration(
          color: barColor,
          border: Border(
            top: BorderSide(color: _lightGreen.withValues(alpha: 0.4), width: 1.5),
          ),
        ),
        child: Row(
          children: [
            if (_voiceStatus == VoiceHardwareStatus.recording)
              ScaleTransition(
                scale: _pulseAnimation,
                child: Icon(Icons.fiber_manual_record, color: Colors.white, size: isCompactHeight ? 16 : 20),
              )
            else
              Icon(icon, color: Colors.white, size: isCompactHeight ? 16 : 20),
            SizedBox(width: isCompactHeight ? 8 : 12),
            Expanded(
              child: Text(
                statusMessage,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: isCompactHeight ? 12 : 14,
                  fontWeight: FontWeight.w600,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAccessibleHardwareCards(bool isTamil, {bool isCompactHeight = false}) {
    return Container(
      color: const Color(0xFF16322C),
      padding: EdgeInsets.symmetric(
        horizontal: 8,
        vertical: isCompactHeight ? 4 : 8,
      ),
      child: Row(
        children: [
          // On-Screen Mic Button Card (Click to start/stop recording, synchronized with ESP32 button)
          Expanded(
            child: InkWell(
              onTap: handlePhysicalVoiceSelectorPress,
              borderRadius: BorderRadius.circular(10),
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: 4,
                  vertical: isCompactHeight ? 4 : 8,
                ),
                decoration: BoxDecoration(
                  color: _voiceStatus == VoiceHardwareStatus.recording
                      ? const Color(0xFF9E1B1B)
                      : const Color(0xFF1E433B),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: _voiceStatus == VoiceHardwareStatus.recording
                        ? Colors.red
                        : _lightGreen.withValues(alpha: 0.45),
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      _voiceStatus == VoiceHardwareStatus.recording ? Icons.mic : Icons.mic_none,
                      color: _voiceStatus == VoiceHardwareStatus.recording ? Colors.white : _lightGreen,
                      size: isCompactHeight ? 14 : 16,
                    ),
                    const SizedBox(width: 4),
                    Flexible(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          _voiceStatus == VoiceHardwareStatus.recording
                              ? (isTamil ? 'நிறுத்து (Stop)' : 'STOP MIC')
                              : (isTamil ? 'பேசுக (Mic)' : 'MIC (Speak)'),
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: isCompactHeight ? 9.5 : 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),

          // Repeat Voice reference
          Expanded(
            child: InkWell(
              onTap: handlePhysicalRepeatVoicePress,
              borderRadius: BorderRadius.circular(10),
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: 4,
                  vertical: isCompactHeight ? 4 : 8,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E433B),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: _lightGreen.withValues(alpha: 0.45)),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.replay, color: _lightGreen, size: isCompactHeight ? 14 : 16),
                    const SizedBox(width: 4),
                    Flexible(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          isTamil ? 'மீண்டும் ஒலி (Repeat Voice)' : 'REPEAT VOICE',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: isCompactHeight ? 9.5 : 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(width: 6),

          // Back reference
          Expanded(
            child: InkWell(
              onTap: handlePhysicalBackPress,
              borderRadius: BorderRadius.circular(10),
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: 4,
                  vertical: isCompactHeight ? 4 : 8,
                ),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E433B),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: _lightGreen.withValues(alpha: 0.45)),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.arrow_back, color: _lightGreen, size: isCompactHeight ? 14 : 16),
                    const SizedBox(width: 4),
                    Flexible(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          isTamil ? 'பின்னால் (Back)' : 'BACK',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: isCompactHeight ? 9.5 : 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// =============================================================================
// MODULAR LISTENING / RECORDING ANIMATION
// =============================================================================

/// Displays a centered, medium-sized animated microphone visual with subtle
/// expanding audio-wave rings and soft emerald glow during active voice recording.
///
/// Features:
/// - Reuses CIVI theme: Deep Forest (#124E43), Emerald (#2D8C75), Light Green (#EAF3EF).
/// - Non-interactive (wrapped in [IgnorePointer]).
/// - Displays duration counter and localized status tag.
/// - Automatically disposes its [AnimationController] when unmounted.
class CiviListeningVisual extends StatefulWidget {
  final bool isTamil;
  final int? seconds;
  final VoidCallback? onTap;

  const CiviListeningVisual({
    super.key,
    required this.isTamil,
    this.seconds,
    this.onTap,
  });

  @override
  State<CiviListeningVisual> createState() => _CiviListeningVisualState();
}

class _CiviListeningVisualState extends State<CiviListeningVisual>
    with SingleTickerProviderStateMixin {
  late final AnimationController _waveController;

  static const Color _deepForest = Color(0xFF1B5E52);
  static const Color _emerald = Color(0xFF329881);
  static const Color _lightGreen = Color(0xFFEEF6F2);

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1600),
    )..repeat();
  }

  @override
  void dispose() {
    _waveController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final mediaQuery = MediaQuery.of(context);
    final isCompactHeight = mediaQuery.orientation == Orientation.landscape && mediaQuery.size.height < 500;

    final visualContainerSize = isCompactHeight ? 96.0 : 150.0;
    final ringBaseSize = isCompactHeight ? 56.0 : 86.0;
    final glowSize = isCompactHeight ? 58.0 : 88.0;
    final coreSize = isCompactHeight ? 50.0 : 76.0;
    final micIconSize = isCompactHeight ? 26.0 : 38.0;

    final visualContent = Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: visualContainerSize,
            height: visualContainerSize,
            child: AnimatedBuilder(
              animation: _waveController,
              builder: (context, child) {
                final progress = _waveController.value;

                // Wave ring 1
                final wave1Scale = 1.0 + (progress * 0.45);
                final wave1Opacity = ((1.0 - progress) * 0.45).clamp(0.0, 1.0);

                // Wave ring 2 (offset phase)
                final wave2Progress = (progress + 0.5) % 1.0;
                final wave2Scale = 1.0 + (wave2Progress * 0.45);
                final wave2Opacity = ((1.0 - wave2Progress) * 0.45).clamp(0.0, 1.0);

                return Stack(
                  alignment: Alignment.center,
                  children: [
                    // Outer Audio-wave ring 1
                    Transform.scale(
                      scale: wave1Scale,
                      child: Container(
                        width: ringBaseSize,
                        height: ringBaseSize,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: _emerald.withValues(alpha: wave1Opacity),
                            width: isCompactHeight ? 2.0 : 3.0,
                          ),
                        ),
                      ),
                    ),
                    // Outer Audio-wave ring 2
                    Transform.scale(
                      scale: wave2Scale,
                      child: Container(
                        width: ringBaseSize,
                        height: ringBaseSize,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: _lightGreen.withValues(alpha: wave2Opacity),
                            width: isCompactHeight ? 1.5 : 2.0,
                          ),
                        ),
                      ),
                    ),
                    // Ambient emerald glow
                    Container(
                      width: glowSize,
                      height: glowSize,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: _emerald.withValues(alpha: 0.4),
                            blurRadius: isCompactHeight ? 14 : 22,
                            spreadRadius: isCompactHeight ? 2 : 4,
                          ),
                        ],
                      ),
                    ),
                    // Center Mic Core Circle
                    Container(
                      width: coreSize,
                      height: coreSize,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [_deepForest, _emerald],
                        ),
                        border: Border.all(
                          color: _lightGreen,
                          width: isCompactHeight ? 2.0 : 2.5,
                        ),
                      ),
                      child: Center(
                        child: Icon(
                          Icons.mic,
                          color: Colors.white,
                          size: micIconSize,
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
          SizedBox(height: isCompactHeight ? 6 : 10),
          // Floating Status Pill Badge
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: isCompactHeight ? 10 : 14,
              vertical: isCompactHeight ? 4 : 6,
            ),
            decoration: BoxDecoration(
              color: _deepForest.withValues(alpha: 0.94),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                color: _lightGreen.withValues(alpha: 0.5),
                width: 1.2,
              ),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.3),
                  blurRadius: 10,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: isCompactHeight ? 6 : 8,
                  height: isCompactHeight ? 6 : 8,
                  decoration: const BoxDecoration(
                    color: Color(0xFFEF5350), // Recording indicator dot
                    shape: BoxShape.circle,
                  ),
                ),
                SizedBox(width: isCompactHeight ? 6 : 8),
                Text(
                  widget.isTamil
                      ? (widget.seconds != null && widget.seconds! > 0
                          ? 'கேட்கிறது (Listening) (${widget.seconds}s)...'
                          : 'கேட்கிறது (Listening)...')
                      : (widget.seconds != null && widget.seconds! > 0
                          ? 'Listening (${widget.seconds}s)...'
                          : 'Listening...'),
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: isCompactHeight ? 10.5 : 12,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );

    if (widget.onTap != null) {
      return GestureDetector(
        onTap: widget.onTap,
        behavior: HitTestBehavior.deferToChild,
        child: visualContent,
      );
    }

    return IgnorePointer(
      child: visualContent,
    );
  }
}

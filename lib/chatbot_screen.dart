import 'dart:async';
import 'package:material_ui/material_ui.dart';
import 'package:flutter/services.dart';
import 'language_selection_screen.dart';
import 'accessibility_confirmation_screen.dart';

/// Models a message in the CIVI legal conversation.
class CiviChatMessage {
  final String text;
  final bool isUser;
  final bool isVoice;
  final String? sourceReference;
  final DateTime timestamp;

  const CiviChatMessage({
    required this.text,
    required this.isUser,
    this.isVoice = false,
    this.sourceReference,
    required this.timestamp,
  });
}

/// Represents the hardware voice interaction state.
enum VoiceHardwareStatus {
  idle,
  recording,
  processing,
  speaking,
  replaying,
}

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

  final List<CiviChatMessage> _messages = [];
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _inputFocusNode = FocusNode();

  VoiceHardwareStatus _voiceStatus = VoiceHardwareStatus.idle;
  int _recordingSeconds = 0;
  Timer? _recordingTimer;
  Timer? _statusTransitionTimer;
  bool _isSessionReset = false;

  late final AnimationController _pulseController;
  late final Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    // Register global hardware keyboard shortcut handler for persistent M, R, B responses
    HardwareKeyboard.instance.addHandler(_handleHardwareKeyEvent);
    _loadInitialSampleConversation();

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
    _recordingTimer?.cancel();
    _statusTransitionTimer?.cancel();
    _textController.dispose();
    _scrollController.dispose();
    _inputFocusNode.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  void _loadInitialSampleConversation() {
    final isTamil = widget.language == CiviLanguage.tamil;
    _messages.clear();
    _messages.add(
      CiviChatMessage(
        text: isTamil
            ? 'வேளாண் கூட்டுறவு சங்கத்தில் உறுப்பினராக சேர தேவையான தகுதிகள் என்ன?'
            : 'What are the key qualifications required to become a member of an agricultural cooperative society?',
        isUser: true,
        timestamp: DateTime.now().subtract(const Duration(minutes: 2)),
      ),
    );
    _messages.add(
      CiviChatMessage(
        text: isTamil
            ? 'தமிழ்நாடு கூட்டுறவு சங்கங்கள் சட்டம் 1983, பிரிவு 21-ன் படி முக்கிய தகுதிகள்:\n\n'
                '• **வயது & வசிப்பிடம்:** 18 வயது பூர்த்தியடைந்தவராகவும், சங்கத்தின் செயல்பாட்டு எல்லைக்குள் வசிப்பவராகவும் இருக்க வேண்டும்.\n'
                '• **விவசாய நிலம்:** சங்க எல்லைக்குள் விவசாய நிலம் சொந்தமாக வைத்திருக்க வேண்டும் அல்லது விவசாயத் தொழில் செய்பவராக இருக்க வேண்டும்.\n'
                '• **தகுதியின்மை:** நொடிப்புநிலை அடையாதவராகவும், குற்றவியல் வழக்குகளில் தண்டனை பெறாதவராகவும் இருத்தல் வேண்டும்.\n\n'
                '*குறிப்பு: விண்ணப்பம் சமர்ப்பித்த 60 நாட்களுக்குள் சங்கம் உரிய முடிவை அறிவிக்க வேண்டும்.*'
            : 'Under Section 21 of the Tamil Nadu Cooperative Societies Act, 1983, primary qualifications include:\n\n'
                '• **Age & Residency:** Individual must have completed 18 years of age and reside within the society’s registered area of operation.\n'
                '• **Agricultural Activity:** Must hold agricultural land or actively carry on agricultural operations within the operational limits.\n'
                '• **Disqualifications:** Must not be an undischarged insolvent or convicted of criminal offenses involving moral turpitude.\n\n'
                '*Statutory Note: The managing committee must dispose of membership applications within 60 days of receipt.*',
        isUser: false,
        sourceReference: isTamil
            ? 'தமிழ்நாடு கூட்டுறவு சங்கங்கள் சட்டம், 1983 — பிரிவு 21, பக்கம் 45'
            : 'Tamil Nadu Cooperative Societies Act, 1983 — Section 21, Page 45',
        timestamp: DateTime.now().subtract(const Duration(minutes: 1)),
      ),
    );
    _isSessionReset = false;
  }

  // ---------------------------------------------------------------------------
  // PHYSICAL HARDWARE BUTTON HOOKS (Ready for ESP32 event integration)
  // ---------------------------------------------------------------------------

  /// Hook for physical button 6: VOICE SELECTOR
  /// 1st Press: Starts recording.
  /// 2nd Press: Stops and submits voice question.
  void handlePhysicalVoiceSelectorPress() {
    if (_voiceStatus == VoiceHardwareStatus.idle) {
      _startVoiceRecording();
    } else if (_voiceStatus == VoiceHardwareStatus.recording) {
      _stopAndSubmitVoiceRecording();
    }
  }

  /// Hook for physical button 5: REPEAT VOICE
  /// Replays the latest CIVI bot answer (never the user question).
  void handlePhysicalRepeatVoicePress() {
    final int index = _messages.lastIndexWhere((m) => !m.isUser);
    if (index == -1) return;

    final latestBotAnswer = _messages[index];
    if (latestBotAnswer.text.isEmpty) return;

    setState(() {
      _voiceStatus = VoiceHardwareStatus.replaying;
    });

    _statusTransitionTimer?.cancel();
    _statusTransitionTimer = Timer(const Duration(milliseconds: 3200), () {
      if (!mounted) return;
      setState(() {
        _voiceStatus = VoiceHardwareStatus.idle;
      });
    });
  }

  /// Hook for physical button 4: BACK
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

  /// Hook for Session Reset.
  void handlePhysicalResetPress() {
    _inputFocusNode.unfocus();
    setState(() {
      _messages.clear();
      _textController.clear();
      _voiceStatus = VoiceHardwareStatus.idle;
      _recordingTimer?.cancel();
      _statusTransitionTimer?.cancel();
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

  void _startVoiceRecording() {
    _inputFocusNode.unfocus();
    _statusTransitionTimer?.cancel();
    setState(() {
      _voiceStatus = VoiceHardwareStatus.recording;
      _recordingSeconds = 0;
    });

    _recordingTimer?.cancel();
    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() {
        _recordingSeconds++;
      });
    });
  }

  void _stopAndSubmitVoiceRecording() {
    _recordingTimer?.cancel();
    setState(() {
      _voiceStatus = VoiceHardwareStatus.processing;
    });

    final isTamil = widget.language == CiviLanguage.tamil;

    // Simulate voice question processing and answer retrieval
    _statusTransitionTimer = Timer(const Duration(milliseconds: 1800), () {
      if (!mounted) return;

      final voiceUserQuestion = CiviChatMessage(
        text: isTamil
            ? 'கூட்டுறவு சங்க நிர்வாகக் குழுவின் பணிக்காலம் எவ்வளவு?'
            : 'What is the tenure of the elected managing committee in a cooperative society?',
        isUser: true,
        isVoice: true,
        timestamp: DateTime.now(),
      );

      final voiceBotAnswer = CiviChatMessage(
        text: isTamil
            ? 'தமிழ்நாடு கூட்டுறவு சங்கங்கள் சட்டம் 1983, பிரிவு 33-ன் படி:\n\n'
                '• தேர்ந்தெடுக்கப்பட்ட நிர்வாகக் குழுவின் பதவிக்காலம் அதன் முதல் கூட்ட தேதியிலிருந்து **ஐந்து ஆண்டுகள் (5 Years)** ஆகும்.\n'
                '• பதவிக்காலம் முடிவடைவதற்கு முன் புதிய குழுவிற்கான தேர்தல் முறையாக நடத்தப்பட வேண்டும்.'
            : 'Under Section 33 of the Tamil Nadu Cooperative Societies Act, 1983:\n\n'
                '• The term of office of the elected members of the board shall be **five years (5 Years)** from the date of election.\n'
                '• Fresh elections must be conducted before the expiration of the current committee’s tenure.',
        isUser: false,
        isVoice: true,
        sourceReference: isTamil
            ? 'தமிழ்நாடு கூட்டுறவு சங்கங்கள் சட்டம், 1983 — பிரிவு 33, பக்கம் 68'
            : 'Tamil Nadu Cooperative Societies Act, 1983 — Section 33, Page 68',
        timestamp: DateTime.now(),
      );

      setState(() {
        _messages.add(voiceUserQuestion);
        _messages.add(voiceBotAnswer);
        _isSessionReset = false;
        _voiceStatus = VoiceHardwareStatus.speaking;
      });

      _scrollToBottom();

      // Automatically speak the voice question's answer, then return to idle
      _statusTransitionTimer = Timer(const Duration(milliseconds: 3500), () {
        if (!mounted) return;
        setState(() {
          _voiceStatus = VoiceHardwareStatus.idle;
        });
      });
    });
  }

  void _handleSendTypedMessage() {
    final text = _textController.text.trim();
    if (text.isEmpty) return;

    final isTamil = widget.language == CiviLanguage.tamil;

    setState(() {
      _messages.add(
        CiviChatMessage(
          text: text,
          isUser: true,
          isVoice: false,
          timestamp: DateTime.now(),
        ),
      );
      _isSessionReset = false;
      _textController.clear();
    });

    // Unfocus text input so keyboard shortcuts (M, R, B) become active immediately
    _inputFocusNode.unfocus();

    _scrollToBottom();

    // Typed questions produce text answers only (not spoken)
    Future.delayed(const Duration(milliseconds: 700), () {
      if (!mounted) return;
      setState(() {
        _messages.add(
          CiviChatMessage(
            text: isTamil
                ? 'உங்கள் வினவல் பதிவு செய்யப்பட்டுள்ளது: "$text".\n\n'
                    'கூட்டுறவு சங்க விதிகளின்படி, குறிப்பிட்ட விதிமுறைகள் மற்றும் அதிகாரப்பூர்வ ஆவணங்களை சரிபார்க்கவும்.'
                : 'Your legal inquiry regarding "$text" has been recorded.\n\n'
                    'According to applicable cooperative governance regulations, statutory procedures must be verified against official notifications.',
            isUser: false,
            isVoice: false,
            sourceReference: isTamil
                ? 'கூட்டுறவு சங்க வழிகாட்டுதல்கள் (பொது விதிமுறை)'
                : 'Cooperative Governance Guidelines (General Section)',
            timestamp: DateTime.now(),
          ),
        );
      });
      _scrollToBottom();
    });
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
                    _buildHeader(isTamil),

                    // 2. Legal Disclaimer banner
                    _buildLegalDisclaimer(isTamil),

                    // 3. Conversation Message Area
                    Expanded(
                      child: _messages.isEmpty
                          ? _buildEmptyState(isTamil)
                          : ListView.builder(
                              controller: _scrollController,
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                              itemCount: _messages.length,
                              itemBuilder: (context, index) {
                                return _buildMessageItem(_messages[index]);
                              },
                            ),
                    ),

                    // 4. Hardware Voice Status Indicator
                    _buildVoiceStatusBar(isTamil),

                    // 5. Text Input Area (with on-screen microphone button)
                    _buildTextInputArea(isTamil),
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

  Widget _buildHeader(bool isTamil) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
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
            icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 20),
            onPressed: handlePhysicalBackPress,
          ),

          // CIVI Brand Logo - noticeably enlarged and naturally blended
          Image.asset(
            'assets/images/civi_logo.png',
            height: 48,
            fit: BoxFit.contain,
            errorBuilder: (context, error, stackTrace) {
              return const Text(
                'CIVI',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                  fontSize: 22,
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
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: _emerald,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        isTamil ? 'நிலையான பயன்முறை' : 'Standard Mode',
                        style: const TextStyle(color: Colors.white, fontSize: 10),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        isTamil ? 'தமிழ்' : 'English',
                        style: TextStyle(color: _lightGreen.withValues(alpha: 0.8), fontSize: 11),
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
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: handlePhysicalResetPress,
          ),
        ],
      ),
    );
  }

  Widget _buildLegalDisclaimer(bool isTamil) {
    return Container(
      width: double.infinity,
      color: const Color(0xFFFFF9E6),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.gavel, size: 16, color: Color(0xFF8A6D3B)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isTamil
                  ? 'தகவல் அறிவிப்பு: CIVI கூட்டுறவு சட்டம் பற்றிய வழிகாட்டுதலை மட்டுமே வழங்குகிறது; இது சான்றளிக்கப்பட்ட வழக்கறிஞர் ஆலோசனை அல்ல.'
                  : 'Notice: CIVI provides informational legal guidance on cooperative governance, not certified legal counsel. Verify with official statutory gazettes.',
              style: const TextStyle(
                fontSize: 11,
                color: Color(0xFF8A6D3B),
                height: 1.3,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState(bool isTamil) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.chat_bubble_outline, size: 48, color: _emerald.withValues(alpha: 0.4)),
            const SizedBox(height: 12),
            Text(
              isTamil
                  ? 'உரையாடல் மீட்டமைக்கப்பட்டது.\nகீழே தட்டச்சு செய்யவும் அல்லது கேள்வி கேட்க ஒலிவாங்கி (Mic) பொத்தானை அழுத்தவும்.'
                  : 'Session is clear.\nType your question below or press the Mic button to speak.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Colors.black.withValues(alpha: 0.5),
                fontSize: 13,
                height: 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMessageItem(CiviChatMessage msg) {
    final screenWidth = MediaQuery.of(context).size.width;
    final isCompact = screenWidth < 400;

    if (msg.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          constraints: BoxConstraints(maxWidth: screenWidth * 0.84),
          margin: EdgeInsets.only(left: isCompact ? 20 : 40, bottom: 10),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
                style: const TextStyle(color: Colors.white, fontSize: 14, height: 1.35),
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
        margin: EdgeInsets.only(right: isCompact ? 18 : 32, bottom: 12),
        padding: const EdgeInsets.all(15),
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
            // Source reference and statutory page number (displayed ONLY if available)
            if (msg.sourceReference != null) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: _lightGreen.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: _emerald.withValues(alpha: 0.3)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.menu_book, size: 14, color: _deepForest),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        msg.sourceReference!,
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
          ],
        ),
      ),
    );
  }

  Widget _buildVoiceStatusBar(bool isTamil) {
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
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Row(
          children: [
            if (_voiceStatus == VoiceHardwareStatus.recording)
              ScaleTransition(
                scale: _pulseAnimation,
                child: const Icon(Icons.fiber_manual_record, color: Colors.white, size: 16),
              )
            else
              Icon(icon, color: Colors.white, size: 16),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                statusMessage,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTextInputArea(bool isTamil) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
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
              width: 38,
              height: 38,
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
                  size: 20,
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
              decoration: InputDecoration(
                hintText: isTamil
                    ? 'சட்டக் கேள்வியை இங்கே தட்டச்சு செய்யவும்...'
                    : 'Type your legal question here...',
                hintStyle: TextStyle(
                  color: Colors.black.withValues(alpha: 0.4),
                  fontSize: 13,
                ),
                contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
            width: 44,
            height: 44,
            child: ElevatedButton(
              onPressed: _handleSendTypedMessage,
              style: ElevatedButton.styleFrom(
                backgroundColor: _deepForest,
                foregroundColor: Colors.white,
                padding: EdgeInsets.zero,
                shape: const CircleBorder(),
                elevation: 2,
              ),
              child: const Icon(Icons.send, size: 18),
            ),
          ),
        ],
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

  final List<CiviChatMessage> _messages = [];
  final ScrollController _scrollController = ScrollController();

  VoiceHardwareStatus _voiceStatus = VoiceHardwareStatus.idle;
  int _recordingSeconds = 0;
  Timer? _recordingTimer;
  Timer? _statusTransitionTimer;

  late final AnimationController _pulseController;
  late final Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    // Register global hardware keyboard shortcut handler for persistent M, R, B responses
    HardwareKeyboard.instance.addHandler(_handleHardwareKeyEvent);
    _loadInitialConversation();

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.9, end: 1.1).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  void _loadInitialConversation() {
    final isTamil = widget.language == CiviLanguage.tamil;
    _messages.clear();
    _messages.add(
      CiviChatMessage(
        text: isTamil
            ? 'வணக்கம்! CIVI குரல்வழியாக உதவ தயாராக உள்ளது.\n\nகேள்வி கேட்க: பேசத் தொடங்குங்கள் (Start Speaking) – ஒலிவாங்கி (Mic) பொத்தானை அல்லது "M" விசையை அழுத்தவும்.'
            : 'Welcome! CIVI Voice Assistant is ready.\n\nTo ask a question: Start Speaking – Press the Mic button or the "M" key to speak.',
        isUser: false,
        isVoice: true,
        timestamp: DateTime.now(),
      ),
    );
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_handleHardwareKeyEvent);
    _recordingTimer?.cancel();
    _statusTransitionTimer?.cancel();
    _scrollController.dispose();
    _pulseController.dispose();
    super.dispose();
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
  // PHYSICAL HARDWARE BUTTON HOOKS (Ready for ESP32 event integration)
  // ---------------------------------------------------------------------------

  /// Hook for physical button 6: VOICE SELECTOR
  void handlePhysicalVoiceSelectorPress() {
    if (_voiceStatus == VoiceHardwareStatus.idle) {
      _startVoiceRecording();
    } else if (_voiceStatus == VoiceHardwareStatus.recording) {
      _stopAndSubmitVoiceRecording();
    }
  }

  /// Hook for physical button 5: REPEAT VOICE
  /// Replays the latest CIVI answer (never the user question).
  void handlePhysicalRepeatVoicePress() {
    final int index = _messages.lastIndexWhere((m) => !m.isUser);
    if (index == -1) return;

    final latestBotAnswer = _messages[index];
    if (latestBotAnswer.text.isEmpty) return;

    setState(() {
      _voiceStatus = VoiceHardwareStatus.replaying;
    });

    _statusTransitionTimer?.cancel();
    _statusTransitionTimer = Timer(const Duration(milliseconds: 3600), () {
      if (!mounted) return;
      setState(() {
        _voiceStatus = VoiceHardwareStatus.idle;
      });
    });
  }

  /// Hook for physical button 4: BACK
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
    setState(() {
      _loadInitialConversation();
      _voiceStatus = VoiceHardwareStatus.idle;
      _recordingTimer?.cancel();
      _statusTransitionTimer?.cancel();
    });

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

  void _startVoiceRecording() {
    _statusTransitionTimer?.cancel();
    setState(() {
      _voiceStatus = VoiceHardwareStatus.recording;
      _recordingSeconds = 0;
    });

    _recordingTimer?.cancel();
    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }
      setState(() {
        _recordingSeconds++;
      });
    });
  }

  void _stopAndSubmitVoiceRecording() {
    _recordingTimer?.cancel();
    setState(() {
      _voiceStatus = VoiceHardwareStatus.processing;
    });

    final isTamil = widget.language == CiviLanguage.tamil;

    // Simulate voice question processing (Speech-to-Text conversion) and response generation
    _statusTransitionTimer = Timer(const Duration(milliseconds: 2000), () {
      if (!mounted) return;

      // 1. Speech-to-Text converted question displayed as normal user message
      final voiceUserQuestion = CiviChatMessage(
        text: isTamil
            ? 'கூட்டுறவு சங்க நிர்வாகக் குழுவின் பணிக்காலம் எவ்வளவு?'
            : 'What is the tenure of the elected managing committee in a cooperative society?',
        isUser: true,
        isVoice: true,
        timestamp: DateTime.now(),
      );

      // 2. Chatbot response displayed as normal CIVI response
      final voiceBotAnswer = CiviChatMessage(
        text: isTamil
            ? 'தமிழ்நாடு கூட்டுறவு சங்கங்கள் சட்டம் 1983 பிரிவு 33-ன் படி:\n\n'
                '• தேர்ந்தெடுக்கப்பட்ட நிர்வாகக் குழுவின் பதவிக்காலம் அதன் முதல் கூட்ட தேதியிலிருந்து **ஐந்து ஆண்டுகள் (5 Years)** ஆகும்.\n'
                '• பதவிக்காலம் நிறைவடையும் முன் புதிய குழுவிற்கான தேர்தல் முறையாக நடத்தப்பட வேண்டும்.'
            : 'Under Section 33 of the Tamil Nadu Cooperative Societies Act, 1983:\n\n'
                '• The term of office of the elected members of the board shall be **five years (5 Years)** from the date of election.\n'
                '• Fresh elections must be conducted before the expiration of the current committee’s tenure.',
        isUser: false,
        isVoice: true,
        sourceReference: isTamil
            ? 'தமிழ்நாடு கூட்டுறவு சங்கங்கள் சட்டம், 1983 — பிரிவு 33'
            : 'Tamil Nadu Cooperative Societies Act, 1983 — Section 33',
        timestamp: DateTime.now(),
      );

      setState(() {
        _messages.add(voiceUserQuestion);
        _messages.add(voiceBotAnswer);
        _voiceStatus = VoiceHardwareStatus.speaking;
      });

      _scrollToBottom();

      // Answers generated from voice questions are automatically spoken in this mode
      _statusTransitionTimer = Timer(const Duration(milliseconds: 4000), () {
        if (!mounted) return;
        setState(() {
          _voiceStatus = VoiceHardwareStatus.idle;
        });
      });
    });
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
                  _buildAccessibleHeader(isTamil),

                  // 2. Conversation Area (Natural conversational chat bubbles)
                  Expanded(
                    child: ListView.builder(
                      controller: _scrollController,
                      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
                      itemCount: _messages.length,
                      itemBuilder: (context, index) {
                        return _buildAccessibleMessageBubble(_messages[index]);
                      },
                    ),
                  ),

                  // 3. Hardware Voice Status Bar
                  _buildAccessibleVoiceStatusBar(isTamil),

                  // 4. Hardware Reference Guidance Cards (No text input in this mode)
                  _buildAccessibleHardwareCards(isTamil),
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

  Widget _buildAccessibleHeader(bool isTamil) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
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
            icon: Icon(Icons.arrow_back_ios_new, color: _lightGreen, size: 20),
            onPressed: handlePhysicalBackPress,
          ),

          // CIVI Brand Logo in accessible top-left header - noticeably enlarged and naturally blended
          Image.asset(
            'assets/images/civi_logo.png',
            height: 48,
            fit: BoxFit.contain,
            errorBuilder: (context, error, stackTrace) {
              return const Text(
                'CIVI',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                  fontSize: 22,
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
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
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
                    fontSize: 11,
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
            icon: const Icon(Icons.refresh, color: Colors.white, size: 24),
            onPressed: handlePhysicalResetPress,
          ),
        ],
      ),
    );
  }

  /// Builds natural conversational chat bubbles with large readable typography.
  /// Does not explicitly label messages as "Question", "Answer", "User Question" or "Bot Answer".
  Widget _buildAccessibleMessageBubble(CiviChatMessage msg) {
    if (msg.isUser) {
      // User chat bubble (speech-to-text converted question)
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(left: 36, bottom: 14),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
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
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
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
        margin: const EdgeInsets.only(right: 30, bottom: 16),
        padding: const EdgeInsets.all(18),
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
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w500,
                height: 1.45,
              ),
            ),
            if (msg.sourceReference != null) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.4),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: _lightGreen.withValues(alpha: 0.4)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.menu_book, size: 15, color: _lightGreen),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        msg.sourceReference!,
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
          ],
        ),
      ),
    );
  }

  Widget _buildAccessibleVoiceStatusBar(bool isTamil) {
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
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
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
                child: const Icon(Icons.fiber_manual_record, color: Colors.white, size: 20),
              )
            else
              Icon(icon, color: Colors.white, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                statusMessage,
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
    );
  }

  Widget _buildAccessibleHardwareCards(bool isTamil) {
    return Container(
      color: const Color(0xFF16322C),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
      child: Row(
        children: [
          // On-Screen Mic Button Card (Click to start/stop recording, synchronized with ESP32 button)
          Expanded(
            child: InkWell(
              onTap: handlePhysicalVoiceSelectorPress,
              borderRadius: BorderRadius.circular(10),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
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
                      size: 16,
                    ),
                    const SizedBox(width: 4),
                    Flexible(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          _voiceStatus == VoiceHardwareStatus.recording
                              ? (isTamil ? 'நிறுத்து (Stop)' : 'STOP MIC')
                              : (isTamil ? 'பேசுக (Mic)' : 'MIC (Speak)'),
                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600),
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
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E433B),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: _lightGreen.withValues(alpha: 0.45)),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.replay, color: _lightGreen, size: 16),
                    const SizedBox(width: 4),
                    Flexible(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          isTamil ? 'மீண்டும் ஒலி (Repeat Voice)' : 'REPEAT VOICE',
                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600),
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
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E433B),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: _lightGreen.withValues(alpha: 0.45)),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(Icons.arrow_back, color: _lightGreen, size: 16),
                    const SizedBox(width: 4),
                    Flexible(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Text(
                          isTamil ? 'பின்னால் (Back)' : 'BACK',
                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600),
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
    final visualContent = Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: 150,
            height: 150,
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
                        width: 86,
                        height: 86,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: _emerald.withValues(alpha: wave1Opacity),
                            width: 3.0,
                          ),
                        ),
                      ),
                    ),
                    // Outer Audio-wave ring 2
                    Transform.scale(
                      scale: wave2Scale,
                      child: Container(
                        width: 86,
                        height: 86,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: _lightGreen.withValues(alpha: wave2Opacity),
                            width: 2.0,
                          ),
                        ),
                      ),
                    ),
                    // Ambient emerald glow
                    Container(
                      width: 88,
                      height: 88,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: _emerald.withValues(alpha: 0.4),
                            blurRadius: 22,
                            spreadRadius: 4,
                          ),
                        ],
                      ),
                    ),
                    // Center Mic Core Circle
                    Container(
                      width: 76,
                      height: 76,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [_deepForest, _emerald],
                        ),
                        border: Border.all(
                          color: _lightGreen,
                          width: 2.5,
                        ),
                      ),
                      child: const Center(
                        child: Icon(
                          Icons.mic,
                          color: Colors.white,
                          size: 38,
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
          const SizedBox(height: 10),
          // Floating Status Pill Badge
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
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
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    color: Color(0xFFEF5350), // Recording indicator dot
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  widget.isTamil
                      ? (widget.seconds != null && widget.seconds! > 0
                          ? 'கேட்கிறது (Listening) (${widget.seconds}s)...'
                          : 'கேட்கிறது (Listening)...')
                      : (widget.seconds != null && widget.seconds! > 0
                          ? 'Listening (${widget.seconds}s)...'
                          : 'Listening...'),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 12,
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

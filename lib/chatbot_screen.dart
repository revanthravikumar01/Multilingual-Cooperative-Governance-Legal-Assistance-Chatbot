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
  // Theme colors
  static const Color _deepForest = Color(0xFF124E43);
  static const Color _emerald = Color(0xFF2D8C75);
  static const Color _lightGreen = Color(0xFFEAF3EF);

  final List<CiviChatMessage> _messages = [];
  final TextEditingController _textController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _focusNode = FocusNode();

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
    _recordingTimer?.cancel();
    _statusTransitionTimer?.cancel();
    _textController.dispose();
    _scrollController.dispose();
    _focusNode.dispose();
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
  /// 2nd Press (when already reset): Navigates back to Accessibility Confirmation.
  void handlePhysicalBackPress() {
    if (!_isSessionReset && _messages.isNotEmpty) {
      handlePhysicalResetPress();
    } else {
      Navigator.of(context).pop();
    }
  }

  /// Hook for Session Reset.
  void handlePhysicalResetPress() {
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

  void _handleKeyboardEvent(KeyEvent event) {
    if (event is KeyDownEvent) {
      if (event.logicalKey == LogicalKeyboardKey.keyV) {
        handlePhysicalVoiceSelectorPress();
      } else if (event.logicalKey == LogicalKeyboardKey.keyR) {
        handlePhysicalRepeatVoicePress();
      } else if (event.logicalKey == LogicalKeyboardKey.escape ||
          event.logicalKey == LogicalKeyboardKey.keyB) {
        handlePhysicalBackPress();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isTamil = widget.language == CiviLanguage.tamil;

    return Scaffold(
      backgroundColor: const Color(0xFFF4F7F6),
      body: KeyboardListener(
        focusNode: _focusNode,
        autofocus: true,
        onKeyEvent: _handleKeyboardEvent,
        child: SafeArea(
          child: Column(
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

              // 5. Text Input Area (NO on-screen microphone button)
              _buildTextInputArea(isTamil),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(bool isTamil) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
          // Logo placeholder or compact brand indicator
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: _lightGreen.withValues(alpha: 0.4)),
            ),
            child: const Text(
              'CIVI',
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w800,
                fontSize: 16,
                letterSpacing: 2.0,
              ),
            ),
          ),
          const SizedBox(width: 12),

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
                ),
                Row(
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
                    Text(
                      isTamil ? 'தமிழ்' : 'English',
                      style: TextStyle(color: _lightGreen.withValues(alpha: 0.8), fontSize: 11),
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
    if (msg.isUser) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          margin: const EdgeInsets.only(left: 48, bottom: 10),
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
        margin: const EdgeInsets.only(right: 36, bottom: 12),
        padding: const EdgeInsets.all(16),
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
                Text(
                  'Cooperative Legal Guidance',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.black.withValues(alpha: 0.5),
                    fontWeight: FontWeight.w500,
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
    IconData icon = Icons.volume_up;
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
        barColor = const Color(0xFF2E7D32);
        icon = Icons.replay;
        statusMessage = isTamil
            ? 'சமீபத்திய CIVI பதில் மீண்டும் ஒலிக்கிறது...'
            : 'Replaying latest CIVI answer (REPEAT VOICE)...';
        break;
    }

    return Container(
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
          // Visual Mic Indicator (non-interactive, visually indicates voice interaction)
          Container(
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
                  ? 'ஒலிவாங்கி (Mic) நிலை காட்டி'
                  : 'Mic indicator (press physical Mic button)',
              child: Icon(
                _voiceStatus == VoiceHardwareStatus.recording ? Icons.mic : Icons.mic_none,
                size: 20,
                color: _voiceStatus == VoiceHardwareStatus.recording
                    ? Colors.white
                    : _deepForest,
              ),
            ),
          ),

          // Rounded Text Input Field
          Expanded(
            child: TextField(
              controller: _textController,
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
  static const Color _lightGreen = Color(0xFFEAF3EF);

  VoiceHardwareStatus _voiceStatus = VoiceHardwareStatus.idle;
  int _recordingSeconds = 0;
  Timer? _recordingTimer;
  Timer? _statusTransitionTimer;

  String _latestAnswer = '';
  final FocusNode _focusNode = FocusNode();

  late final AnimationController _pulseController;
  late final Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    final isTamil = widget.language == CiviLanguage.tamil;

    _latestAnswer = isTamil
        ? 'CIVI குரல்வழியாக உதவ தயாராக உள்ளது. கேள்வி கேட்க ஒலிவாங்கி (Mic) பொத்தானை ஒருமுறை அழுத்தவும்.'
        : 'CIVI Voice Assistant is ready. Press the Mic button once to speak your legal inquiry.';

    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat(reverse: true);

    _pulseAnimation = Tween<double>(begin: 0.9, end: 1.1).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _recordingTimer?.cancel();
    _statusTransitionTimer?.cancel();
    _focusNode.dispose();
    _pulseController.dispose();
    super.dispose();
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
  void handlePhysicalRepeatVoicePress() {
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
  /// Returns to the Accessibility Confirmation screen.
  void handlePhysicalBackPress() {
    Navigator.of(context).pop();
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

    _statusTransitionTimer = Timer(const Duration(milliseconds: 2000), () {
      if (!mounted) return;

      setState(() {
        _latestAnswer = isTamil
            ? 'கூட்டுறவு சங்க நிர்வாகக் குழுவின் பதவிக்காலம் ஐந்து ஆண்டுகள் ஆகும். தமிழ்நாடு கூட்டுறவு சங்கங்கள் சட்டம் 1983 பிரிவு 33-ன் படி இது நிர்ணயிக்கப்பட்டுள்ளது.'
            : 'The tenure of an elected cooperative society board is five years. This is governed by Section 33 of the Tamil Nadu Cooperative Societies Act, 1983.';
        _voiceStatus = VoiceHardwareStatus.speaking;
      });

      _statusTransitionTimer = Timer(const Duration(milliseconds: 4000), () {
        if (!mounted) return;
        setState(() {
          _voiceStatus = VoiceHardwareStatus.idle;
        });
      });
    });
  }

  void _handleKeyboardEvent(KeyEvent event) {
    if (event is KeyDownEvent) {
      if (event.logicalKey == LogicalKeyboardKey.keyV) {
        handlePhysicalVoiceSelectorPress();
      } else if (event.logicalKey == LogicalKeyboardKey.keyR) {
        handlePhysicalRepeatVoicePress();
      } else if (event.logicalKey == LogicalKeyboardKey.escape ||
          event.logicalKey == LogicalKeyboardKey.keyB) {
        handlePhysicalBackPress();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isTamil = widget.language == CiviLanguage.tamil;

    return Scaffold(
      backgroundColor: const Color(0xFF091A16), // High contrast dark background
      body: KeyboardListener(
        focusNode: _focusNode,
        autofocus: true,
        onKeyEvent: _handleKeyboardEvent,
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Top Header: Visually Challenged Mode Indicator
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                  decoration: BoxDecoration(
                    color: Colors.black,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: _lightGreen, width: 2),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.record_voice_over, color: _lightGreen, size: 28),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Text(
                          isTamil
                              ? 'பார்வைக் குறைபாடு பயன்முறை'
                              : 'VISUALLY CHALLENGED MODE',
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 18,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 1.0,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // Primary Large Status Card
                _buildLargeStatusCard(isTamil),
                const SizedBox(height: 16),

                // Latest Answer Card (Large Readable Typography)
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: const Color(0xFF132B25),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: _lightGreen.withValues(alpha: 0.5), width: 2),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          isTamil ? 'சமீபத்திய பதில்:' : 'LATEST ANSWER:',
                          style: const TextStyle(
                            color: _lightGreen,
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 1.2,
                          ),
                        ),
                        const SizedBox(height: 12),
                        Expanded(
                          child: SingleChildScrollView(
                            child: Text(
                              _latestAnswer,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 22,
                                height: 1.45,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),

                // Hardware Button Reference Guidance Cards
                _buildHardwareInstructions(isTamil),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLargeStatusCard(bool isTamil) {
    Color cardColor = const Color(0xFF132B25);
    String title = '';
    String instruction = '';

    switch (_voiceStatus) {
      case VoiceHardwareStatus.idle:
        title = isTamil ? 'காத்திருப்பு நிலை (IDLE)' : 'READY (IDLE)';
        instruction = isTamil
            ? 'கேள்வி கேட்க ஒலிவாங்கி (Mic) பொத்தானை ஒருமுறை அழுத்தவும்.'
            : 'Press the Mic button once to start speaking.';
        break;
      case VoiceHardwareStatus.recording:
        cardColor = const Color(0xFF8B0000);
        title = isTamil ? 'பதிவாகிறது (${_recordingSeconds}s)' : 'RECORDING (${_recordingSeconds}s)';
        instruction = isTamil
            ? 'சமர்ப்பிக்க மீண்டும் ஒலிவாங்கி (Mic) பொத்தானை அழுத்தவும்.'
            : 'Press the Mic button again to submit.';
        break;
      case VoiceHardwareStatus.processing:
        cardColor = const Color(0xFF1B5E20);
        title = isTamil ? 'ஆய்வு செய்கிறது...' : 'PROCESSING...';
        instruction = isTamil
            ? 'தயவுசெய்து காத்திருக்கவும்.'
            : 'Please wait while answering.';
        break;
      case VoiceHardwareStatus.speaking:
        cardColor = const Color(0xFF0D47A1);
        title = isTamil ? 'பதில் ஒலிக்கிறது...' : 'SPEAKING ANSWER...';
        instruction = isTamil
            ? 'பதில் தற்போது குரல்வழியாக ஒலிக்கிறது.'
            : 'CIVI is speaking the answer.';
        break;
      case VoiceHardwareStatus.replaying:
        cardColor = const Color(0xFF2E7D32);
        title = isTamil ? 'மீண்டும் ஒலிக்கிறது...' : 'REPLAYING...';
        instruction = isTamil
            ? 'சமீபத்திய பதில் மீண்டும் ஒலிக்கிறது.'
            : 'Replaying the latest answer.';
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: _lightGreen, width: 2.5),
      ),
      child: Row(
        children: [
          // Large, highly visible Microphone Visual Indicator
          Container(
            width: 58,
            height: 58,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _voiceStatus == VoiceHardwareStatus.recording
                  ? Colors.red.withValues(alpha: 0.3)
                  : _lightGreen.withValues(alpha: 0.12),
              border: Border.all(
                color: _voiceStatus == VoiceHardwareStatus.recording
                    ? Colors.white
                    : _lightGreen,
                width: 2,
              ),
            ),
            child: Center(
              child: _voiceStatus == VoiceHardwareStatus.recording
                  ? ScaleTransition(
                      scale: _pulseAnimation,
                      child: const Icon(Icons.mic, color: Colors.white, size: 36),
                    )
                  : const Icon(Icons.mic, color: _lightGreen, size: 36),
            ),
          ),
          const SizedBox(width: 18),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  instruction,
                  style: TextStyle(
                    color: _lightGreen.withValues(alpha: 0.9),
                    fontSize: 15,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHardwareInstructions(bool isTamil) {
    return Column(
      children: [
        // Mic Instruction Guidance Card
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: _lightGreen.withValues(alpha: 0.5), width: 1.5),
          ),
          child: Row(
            children: [
              const Icon(Icons.mic, color: _lightGreen, size: 24),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  isTamil
                      ? 'ஒலிவாங்கி (Mic) பொத்தான்: பேச ஒருமுறை, சமர்ப்பிக்க மீண்டும் அழுத்தவும்.'
                      : 'Mic Button: Press once to speak, press again to submit.',
                  style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w500),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),

        // Repeat Voice Instruction Card
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white24),
          ),
          child: Row(
            children: [
              const Icon(Icons.replay, color: _lightGreen, size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  isTamil
                      ? 'REPEAT VOICE பொத்தான்: பதிலை மீண்டும் கேட்கலாம்.'
                      : 'REPEAT VOICE Button: Replays latest answer.',
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),

        // Back Instruction Card
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          decoration: BoxDecoration(
            color: Colors.black,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white24),
          ),
          child: Row(
            children: [
              const Icon(Icons.arrow_back, color: _lightGreen, size: 22),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  isTamil
                      ? 'BACK பொத்தான்: அணுகல் முறைத் தேர்வுக்குத் திரும்பலாம்.'
                      : 'BACK Button: Returns to Accessibility Settings.',
                  style: const TextStyle(color: Colors.white, fontSize: 13),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

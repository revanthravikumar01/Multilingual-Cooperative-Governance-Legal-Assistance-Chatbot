# Multilingual Cooperative Governance & Legal Assistance Chatbot

## 📌 Project Overview

The **Multilingual Cooperative Governance & Legal Assistance Chatbot** is an AI-powered, hardware-integrated assistance system designed to help rural citizens, farmers, and cooperative society members understand cooperative governance, rules, regulations, and legal procedures in their preferred language.

The system uses AI and a Retrieval-Augmented Generation (RAG) approach to provide simple, reliable, and document-based answers to users' queries through both text and voice interactions.

## ✨ Key Features

- **Multilingual Support:** Allows users to interact in their preferred language, initially focusing on Tamil and English.
- **Voice Interaction:** Supports voice-based questions and spoken responses.
- **AI-Powered Chatbot:** Understands user queries and provides easy-to-understand answers.
- **RAG-Based Information Retrieval:** Retrieves relevant information from verified government documents, rules, and legal resources.
- **Cooperative Governance Assistance:** Provides guidance on cooperative society procedures, member rights, responsibilities, and regulations.
- **Hardware Integration:** Uses ESP32 and connected peripherals to support physical user interaction.
- **User-Friendly Interface:** Designed to make information accessible to people with limited technical knowledge.

## ⚙️ System Architecture

The project combines two major components:

1. **Hardware:** ESP32-based interaction system with input controls and audio peripherals.
2. **Software:** AI chatbot, multilingual processing, document retrieval, and user interface.
3. **Display:**  Due to financial issues we used our mobile to showcase the interface

## 🎯 Objective

To make cooperative governance and legal information more accessible by providing a simple, multilingual, and user-friendly AI assistance system.

## 🛠️ Technologies

- Python
- Large Language Models (LLMs)
- Retrieval-Augmented Generation (RAG)
- Speech-to-Text and Text-to-Speech
- ESP32
- Web Technologies

## 🚀 Project Goal

To bridge the information gap between cooperative institutions and ordinary citizens through accessible AI-powered assistance.

## ▶️ Running it (development)

1. **Backend + speech service (laptop):** double-click `start_civi.cmd`, or see [backend/README.md](backend/README.md)
   and [speech_service/README.md](speech_service/README.md) for the one-time setup (Python environments, Gemini key,
   speech models).
2. **Flutter app (phone on the same Wi-Fi):**

   ```powershell
   flutter run --dart-define=CIVI_API_BASE_URL=http://<laptop-wifi-ip>:8000
   ```

   | Option | Default | Meaning |
   |---|---|---|
   | `CIVI_API_BASE_URL` | (required) | The laptop's backend address |
   | `CIVI_KIOSK_ID` | `kiosk-1` | Links the app's conversation to the kiosk's ESP32 (it finds it with `GET /kiosks/{id}/session`) |
   | `CIVI_APP_AUDIO` | `true` | Use the phone's own microphone and speaker for voice. Set `false` once the ESP32 handles audio |

   On Windows, building the app needs **Developer Mode** (Settings → System → For developers), because the
   audio plugins need symbolic links.

How the app works with the backend:

- Each chat screen starts a backend session (with the kiosk ID) and polls its messages every 2 s, so questions
  asked at the kiosk by voice appear in the app too (Decisions 21 and 37).
- **Standard mode:** typed question → written answer; voice question → written + spoken answer.
  **Visually challenged mode:** every answer is spoken (Decision 14).
- Keyboard keys stand in for the kiosk buttons: **M** microphone (press to record, press again to send; stops
  at 60 s), **R** repeat the last spoken answer, **C** confirm (speak the complete answer), **B** back/reset.

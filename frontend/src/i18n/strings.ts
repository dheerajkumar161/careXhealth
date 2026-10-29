/**
 * Built-in translations of the core UI vocabulary, keyed by the English text itself.
 * Anything not listed here (other languages, or dynamic text) is translated by the backend (`POST /api/translate`,
 * cached server-side and in localStorage) and falls back to English if no model is reachable.
 */
export const LANGUAGE_NAMES: Record<string, string> = {
  en: "English", hi: "हिन्दी", bn: "বাংলা", ta: "தமிழ்", te: "తెలుగు", mr: "मराठी", gu: "ગુજરાતી", kn: "ಕನ್ನಡ", ml: "മലയാളം", pa: "ਪੰਜਾਬੀ",
  ur: "اردو", es: "Español", fr: "Français", ar: "العربية", pt: "Português", de: "Deutsch",
};

export const RTL = new Set(["ar", "ur"]);

type Dict = Record<string, string>;

const hi: Dict = {
  Overview: "सारांश", Patients: "मरीज़", Referrals: "रेफ़रल", Tests: "जाँचें", "Alerts & escalations": "अलर्ट और एस्केलेशन", Alerts: "अलर्ट", Handoffs: "हैंडऑफ़",
  Today: "आज", "My care plan": "मेरी देखभाल योजना", Appointments: "अपॉइंटमेंट", Documents: "दस्तावेज़", "Care assistant": "देखभाल सहायक", Schedule: "कार्यक्रम",
  "Profile & settings": "प्रोफ़ाइल और सेटिंग्स", "Audit log": "ऑडिट लॉग", Users: "उपयोगकर्ता", "Sign out": "साइन आउट", Notifications: "सूचनाएँ", New: "नई", Seen: "देखी गई",
  "Mark all as seen": "सभी को देखा हुआ चिह्नित करें", "You're all caught up.": "आप सब देख चुके हैं।", "Nothing seen yet.": "अभी कुछ नहीं देखा।", "Agents live": "एजेंट सक्रिय", workspace: "कार्यक्षेत्र",
  "Personal details": "व्यक्तिगत विवरण", "Full name": "पूरा नाम", Email: "ईमेल", Phone: "फ़ोन", Title: "पद", Address: "पता", "Emergency contact": "आपातकालीन संपर्क", Organization: "संस्था", Location: "स्थान",
  Language: "भाषा", "Choose the language used for your plan, messages and notifications.": "अपनी योजना, संदेशों और सूचनाओं के लिए भाषा चुनें।", "Save changes": "बदलाव सहेजें", Saving: "सहेजा जा रहा है",
  Security: "सुरक्षा", "Change password": "पासवर्ड बदलें", "Current password": "वर्तमान पासवर्ड", "New password": "नया पासवर्ड", "Confirm new password": "नए पासवर्ड की पुष्टि करें",
  "Update password": "पासवर्ड अपडेट करें", "Passwords do not match": "पासवर्ड मेल नहीं खाते", "Profile updated": "प्रोफ़ाइल अपडेट हो गई", "Password updated": "पासवर्ड अपडेट हो गया",
  Role: "भूमिका", Department: "विभाग", Cancel: "रद्द करें", Save: "सहेजें", "Loading…": "लोड हो रहा है…", "Translation is unavailable right now — showing English.": "अनुवाद अभी उपलब्ध नहीं है — अंग्रेज़ी दिखाई जा रही है।",
  "Ask your care assistant": "अपने देखभाल सहायक से पूछें", "My recovery plan": "मेरी रिकवरी योजना", "Your day": "आपका दिन",
};

const bn: Dict = {
  Overview: "সারসংক্ষেপ", Patients: "রোগী", Referrals: "রেফারেল", Tests: "পরীক্ষা", "Alerts & escalations": "সতর্কতা ও এসকেলেশন", Alerts: "সতর্কতা", Handoffs: "হ্যান্ডঅফ",
  Today: "আজ", "My care plan": "আমার যত্ন পরিকল্পনা", Appointments: "অ্যাপয়েন্টমেন্ট", Documents: "নথি", "Care assistant": "যত্ন সহকারী", Schedule: "সময়সূচি",
  "Profile & settings": "প্রোফাইল ও সেটিংস", "Audit log": "অডিট লগ", Users: "ব্যবহারকারী", "Sign out": "সাইন আউট", Notifications: "বিজ্ঞপ্তি", New: "নতুন", Seen: "দেখা হয়েছে",
  "Mark all as seen": "সব দেখা হয়েছে চিহ্নিত করুন", "You're all caught up.": "সবকিছু দেখা হয়ে গেছে।", "Nothing seen yet.": "এখনও কিছু দেখা হয়নি।", "Agents live": "এজেন্ট সক্রিয়", workspace: "ওয়ার্কস্পেস",
  "Personal details": "ব্যক্তিগত তথ্য", "Full name": "পুরো নাম", Email: "ইমেল", Phone: "ফোন", Title: "পদবি", Address: "ঠিকানা", "Emergency contact": "জরুরি যোগাযোগ", Organization: "প্রতিষ্ঠান", Location: "অবস্থান",
  Language: "ভাষা", "Choose the language used for your plan, messages and notifications.": "আপনার পরিকল্পনা, বার্তা ও বিজ্ঞপ্তির ভাষা বেছে নিন।", "Save changes": "পরিবর্তন সংরক্ষণ করুন", Saving: "সংরক্ষণ হচ্ছে",
  Security: "নিরাপত্তা", "Change password": "পাসওয়ার্ড পরিবর্তন", "Current password": "বর্তমান পাসওয়ার্ড", "New password": "নতুন পাসওয়ার্ড", "Confirm new password": "নতুন পাসওয়ার্ড নিশ্চিত করুন",
  "Update password": "পাসওয়ার্ড আপডেট করুন", "Passwords do not match": "পাসওয়ার্ড মিলছে না", "Profile updated": "প্রোফাইল আপডেট হয়েছে", "Password updated": "পাসওয়ার্ড আপডেট হয়েছে",
  Role: "ভূমিকা", Department: "বিভাগ", Cancel: "বাতিল", Save: "সংরক্ষণ", "Loading…": "লোড হচ্ছে…", "Translation is unavailable right now — showing English.": "অনুবাদ এখন পাওয়া যাচ্ছে না — ইংরেজি দেখানো হচ্ছে।",
};

const ta: Dict = {
  Overview: "மேலோட்டம்", Patients: "நோயாளிகள்", Referrals: "பரிந்துரைகள்", Tests: "பரிசோதனைகள்", "Alerts & escalations": "எச்சரிக்கைகள்", Alerts: "எச்சரிக்கைகள்", Handoffs: "ஒப்படைப்புகள்",
  Today: "இன்று", "My care plan": "என் பராமரிப்புத் திட்டம்", Appointments: "சந்திப்புகள்", Documents: "ஆவணங்கள்", "Care assistant": "பராமரிப்பு உதவியாளர்", Schedule: "அட்டவணை",
  "Profile & settings": "சுயவிவரம் & அமைப்புகள்", "Audit log": "தணிக்கைப் பதிவு", Users: "பயனர்கள்", "Sign out": "வெளியேறு", Notifications: "அறிவிப்புகள்", New: "புதியவை", Seen: "பார்த்தவை",
  "Mark all as seen": "அனைத்தையும் பார்த்ததாகக் குறி", "You're all caught up.": "அனைத்தையும் பார்த்துவிட்டீர்கள்.", "Nothing seen yet.": "இன்னும் எதுவும் பார்க்கவில்லை.", "Agents live": "முகவர்கள் செயலில்", workspace: "பணியிடம்",
  "Personal details": "தனிப்பட்ட விவரங்கள்", "Full name": "முழு பெயர்", Email: "மின்னஞ்சல்", Phone: "தொலைபேசி", Title: "பதவி", Address: "முகவரி", "Emergency contact": "அவசரத் தொடர்பு", Organization: "நிறுவனம்", Location: "இடம்",
  Language: "மொழி", "Choose the language used for your plan, messages and notifications.": "உங்கள் திட்டம், செய்திகள், அறிவிப்புகளுக்கான மொழியைத் தேர்ந்தெடுக்கவும்.", "Save changes": "மாற்றங்களைச் சேமி", Saving: "சேமிக்கிறது",
  Security: "பாதுகாப்பு", "Change password": "கடவுச்சொல்லை மாற்று", "Current password": "தற்போதைய கடவுச்சொல்", "New password": "புதிய கடவுச்சொல்", "Confirm new password": "புதிய கடவுச்சொல்லை உறுதிசெய்",
  "Update password": "கடவுச்சொல்லைப் புதுப்பி", "Passwords do not match": "கடவுச்சொற்கள் பொருந்தவில்லை", "Profile updated": "சுயவிவரம் புதுப்பிக்கப்பட்டது", "Password updated": "கடவுச்சொல் புதுப்பிக்கப்பட்டது",
  Role: "பங்கு", Department: "துறை", Cancel: "ரத்து", Save: "சேமி", "Loading…": "ஏற்றுகிறது…", "Translation is unavailable right now — showing English.": "மொழிபெயர்ப்பு இப்போது கிடைக்கவில்லை — ஆங்கிலம் காட்டப்படுகிறது.",
};

const te: Dict = {
  Overview: "అవలోకనం", Patients: "రోగులు", Referrals: "రిఫరల్స్", Tests: "పరీక్షలు", "Alerts & escalations": "హెచ్చరికలు", Alerts: "హెచ్చరికలు", Handoffs: "హ్యాండ్‌ఆఫ్‌లు",
  Today: "ఈ రోజు", "My care plan": "నా సంరక్షణ ప్రణాళిక", Appointments: "అపాయింట్‌మెంట్‌లు", Documents: "పత్రాలు", "Care assistant": "సంరక్షణ సహాయకుడు", Schedule: "షెడ్యూల్",
  "Profile & settings": "ప్రొఫైల్ & సెట్టింగ్‌లు", "Audit log": "ఆడిట్ లాగ్", Users: "వినియోగదారులు", "Sign out": "సైన్ అవుట్", Notifications: "నోటిఫికేషన్‌లు", New: "కొత్తవి", Seen: "చూసినవి",
  "Mark all as seen": "అన్నీ చూసినట్లు గుర్తించు", "You're all caught up.": "అన్నీ చూసేశారు.", "Nothing seen yet.": "ఇంకా ఏదీ చూడలేదు.", "Agents live": "ఏజెంట్లు సక్రియం", workspace: "వర్క్‌స్పేస్",
  "Personal details": "వ్యక్తిగత వివరాలు", "Full name": "పూర్తి పేరు", Email: "ఈమెయిల్", Phone: "ఫోన్", Title: "హోదా", Address: "చిరునామా", "Emergency contact": "అత్యవసర సంప్రదింపు", Organization: "సంస్థ", Location: "ప్రదేశం",
  Language: "భాష", "Choose the language used for your plan, messages and notifications.": "మీ ప్రణాళిక, సందేశాలు, నోటిఫికేషన్‌ల భాషను ఎంచుకోండి.", "Save changes": "మార్పులను సేవ్ చేయి", Saving: "సేవ్ అవుతోంది",
  Security: "భద్రత", "Change password": "పాస్‌వర్డ్ మార్చండి", "Current password": "ప్రస్తుత పాస్‌వర్డ్", "New password": "కొత్త పాస్‌వర్డ్", "Confirm new password": "కొత్త పాస్‌వర్డ్‌ను నిర్ధారించండి",
  "Update password": "పాస్‌వర్డ్ నవీకరించండి", "Passwords do not match": "పాస్‌వర్డ్‌లు సరిపోలడం లేదు", "Profile updated": "ప్రొఫైల్ నవీకరించబడింది", "Password updated": "పాస్‌వర్డ్ నవీకరించబడింది",
  Role: "పాత్ర", Department: "విభాగం", Cancel: "రద్దు", Save: "సేవ్", "Loading…": "లోడ్ అవుతోంది…", "Translation is unavailable right now — showing English.": "అనువాదం ప్రస్తుతం అందుబాటులో లేదు — ఆంగ్లం చూపబడుతోంది.",
};

const mr: Dict = {
  Overview: "आढावा", Patients: "रुग्ण", Referrals: "रेफरल", Tests: "चाचण्या", "Alerts & escalations": "सूचना आणि एस्केलेशन", Alerts: "सूचना", Handoffs: "हस्तांतरण",
  Today: "आज", "My care plan": "माझी काळजी योजना", Appointments: "भेटी", Documents: "कागदपत्रे", "Care assistant": "काळजी सहाय्यक", Schedule: "वेळापत्रक",
  "Profile & settings": "प्रोफाइल आणि सेटिंग्ज", "Audit log": "ऑडिट लॉग", Users: "वापरकर्ते", "Sign out": "साइन आउट", Notifications: "सूचना", New: "नवीन", Seen: "पाहिलेले",
  "Mark all as seen": "सर्व पाहिले म्हणून चिन्हांकित करा", "You're all caught up.": "तुम्ही सर्व पाहिले आहे.", "Nothing seen yet.": "अजून काहीही पाहिले नाही.", "Agents live": "एजंट सक्रिय", workspace: "कार्यक्षेत्र",
  "Personal details": "वैयक्तिक तपशील", "Full name": "पूर्ण नाव", Email: "ईमेल", Phone: "फोन", Title: "पदनाम", Address: "पत्ता", "Emergency contact": "आणीबाणी संपर्क", Organization: "संस्था", Location: "ठिकाण",
  Language: "भाषा", "Choose the language used for your plan, messages and notifications.": "तुमची योजना, संदेश आणि सूचनांसाठी भाषा निवडा.", "Save changes": "बदल जतन करा", Saving: "जतन होत आहे",
  Security: "सुरक्षा", "Change password": "पासवर्ड बदला", "Current password": "सध्याचा पासवर्ड", "New password": "नवीन पासवर्ड", "Confirm new password": "नवीन पासवर्डची पुष्टी करा",
  "Update password": "पासवर्ड अपडेट करा", "Passwords do not match": "पासवर्ड जुळत नाहीत", "Profile updated": "प्रोफाइल अपडेट झाली", "Password updated": "पासवर्ड अपडेट झाला",
  Role: "भूमिका", Department: "विभाग", Cancel: "रद्द करा", Save: "जतन करा", "Loading…": "लोड होत आहे…", "Translation is unavailable right now — showing English.": "भाषांतर सध्या उपलब्ध नाही — इंग्रजी दाखवले जात आहे.",
};

const es: Dict = {
  Overview: "Resumen", Patients: "Pacientes", Referrals: "Derivaciones", Tests: "Pruebas", "Alerts & escalations": "Alertas y escalados", Alerts: "Alertas", Handoffs: "Traspasos",
  Today: "Hoy", "My care plan": "Mi plan de cuidados", Appointments: "Citas", Documents: "Documentos", "Care assistant": "Asistente de cuidados", Schedule: "Agenda",
  "Profile & settings": "Perfil y ajustes", "Audit log": "Registro de auditoría", Users: "Usuarios", "Sign out": "Cerrar sesión", Notifications: "Notificaciones", New: "Nuevas", Seen: "Vistas",
  "Mark all as seen": "Marcar todo como visto", "You're all caught up.": "Estás al día.", "Nothing seen yet.": "Nada visto todavía.", "Agents live": "Agentes activos", workspace: "espacio de trabajo",
  "Personal details": "Datos personales", "Full name": "Nombre completo", Email: "Correo electrónico", Phone: "Teléfono", Title: "Cargo", Address: "Dirección", "Emergency contact": "Contacto de emergencia", Organization: "Organización", Location: "Ubicación",
  Language: "Idioma", "Choose the language used for your plan, messages and notifications.": "Elige el idioma de tu plan, mensajes y notificaciones.", "Save changes": "Guardar cambios", Saving: "Guardando",
  Security: "Seguridad", "Change password": "Cambiar contraseña", "Current password": "Contraseña actual", "New password": "Nueva contraseña", "Confirm new password": "Confirmar nueva contraseña",
  "Update password": "Actualizar contraseña", "Passwords do not match": "Las contraseñas no coinciden", "Profile updated": "Perfil actualizado", "Password updated": "Contraseña actualizada",
  Role: "Rol", Department: "Departamento", Cancel: "Cancelar", Save: "Guardar", "Loading…": "Cargando…", "Translation is unavailable right now — showing English.": "La traducción no está disponible ahora — se muestra en inglés.",
};

const fr: Dict = {
  Overview: "Aperçu", Patients: "Patients", Referrals: "Orientations", Tests: "Examens", "Alerts & escalations": "Alertes et escalades", Alerts: "Alertes", Handoffs: "Transmissions",
  Today: "Aujourd'hui", "My care plan": "Mon plan de soins", Appointments: "Rendez-vous", Documents: "Documents", "Care assistant": "Assistant de soins", Schedule: "Planning",
  "Profile & settings": "Profil et paramètres", "Audit log": "Journal d'audit", Users: "Utilisateurs", "Sign out": "Se déconnecter", Notifications: "Notifications", New: "Nouvelles", Seen: "Vues",
  "Mark all as seen": "Tout marquer comme vu", "You're all caught up.": "Vous êtes à jour.", "Nothing seen yet.": "Rien de vu pour l'instant.", "Agents live": "Agents actifs", workspace: "espace de travail",
  "Personal details": "Informations personnelles", "Full name": "Nom complet", Email: "E-mail", Phone: "Téléphone", Title: "Fonction", Address: "Adresse", "Emergency contact": "Contact d'urgence", Organization: "Organisation", Location: "Lieu",
  Language: "Langue", "Choose the language used for your plan, messages and notifications.": "Choisissez la langue de votre plan, de vos messages et notifications.", "Save changes": "Enregistrer", Saving: "Enregistrement",
  Security: "Sécurité", "Change password": "Changer le mot de passe", "Current password": "Mot de passe actuel", "New password": "Nouveau mot de passe", "Confirm new password": "Confirmer le nouveau mot de passe",
  "Update password": "Mettre à jour le mot de passe", "Passwords do not match": "Les mots de passe ne correspondent pas", "Profile updated": "Profil mis à jour", "Password updated": "Mot de passe mis à jour",
  Role: "Rôle", Department: "Service", Cancel: "Annuler", Save: "Enregistrer", "Loading…": "Chargement…", "Translation is unavailable right now — showing English.": "La traduction est indisponible pour le moment — affichage en anglais.",
};

const ar: Dict = {
  Overview: "نظرة عامة", Patients: "المرضى", Referrals: "الإحالات", Tests: "الفحوصات", "Alerts & escalations": "التنبيهات والتصعيد", Alerts: "التنبيهات", Handoffs: "التسليم",
  Today: "اليوم", "My care plan": "خطة رعايتي", Appointments: "المواعيد", Documents: "المستندات", "Care assistant": "مساعد الرعاية", Schedule: "الجدول",
  "Profile & settings": "الملف الشخصي والإعدادات", "Audit log": "سجل التدقيق", Users: "المستخدمون", "Sign out": "تسجيل الخروج", Notifications: "الإشعارات", New: "جديدة", Seen: "تمت رؤيتها",
  "Mark all as seen": "تعليم الكل كمقروء", "You're all caught up.": "لا توجد إشعارات جديدة.", "Nothing seen yet.": "لا شيء بعد.", "Agents live": "الوكلاء يعملون", workspace: "مساحة العمل",
  "Personal details": "البيانات الشخصية", "Full name": "الاسم الكامل", Email: "البريد الإلكتروني", Phone: "الهاتف", Title: "المسمى", Address: "العنوان", "Emergency contact": "جهة اتصال الطوارئ", Organization: "المؤسسة", Location: "الموقع",
  Language: "اللغة", "Choose the language used for your plan, messages and notifications.": "اختر لغة خطتك ورسائلك وإشعاراتك.", "Save changes": "حفظ التغييرات", Saving: "جارٍ الحفظ",
  Security: "الأمان", "Change password": "تغيير كلمة المرور", "Current password": "كلمة المرور الحالية", "New password": "كلمة المرور الجديدة", "Confirm new password": "تأكيد كلمة المرور الجديدة",
  "Update password": "تحديث كلمة المرور", "Passwords do not match": "كلمتا المرور غير متطابقتين", "Profile updated": "تم تحديث الملف الشخصي", "Password updated": "تم تحديث كلمة المرور",
  Role: "الدور", Department: "القسم", Cancel: "إلغاء", Save: "حفظ", "Loading…": "جارٍ التحميل…", "Translation is unavailable right now — showing English.": "الترجمة غير متاحة حاليًا — يتم عرض الإنجليزية.",
};

export const STATIC: Record<string, Dict> = { hi, bn, ta, te, mr, es, fr, ar };

"""The strings the system says in its own voice, in the user's language.

There are two kinds of text in an answer and they are localised by completely
different means, on purpose.

  * What the SYSTEM says -- "this is background, not law", "the most relevant
    provision says", the abstention, the word "page". This is fixed,
    navigational scaffolding. It is translated ONCE, by hand, into the table
    below, and after that it is deterministic: no model, no latency, no way for
    it to come out wrong on a Tuesday. This module is that table.

  * What the STATUTE says -- the quoted provision. That is never translated at
    all. A translated quote is a paraphrase and a paraphrase is not authority,
    so the quote stays in the language the legislature enacted it in, with a
    line above it in the user's language saying so.

Between those two sits the model's paraphrase, which is handled in
rag/translate.py under a quality gate, because that is the only part a machine
has to write and therefore the only part that can be wrong.

Why a hand-written table rather than a call to the translator for these seven
strings: they are shown on every single answer, including the abstention -- the
answer given when the system has nothing. Having the sentence "I don't have
authority in the corpus to answer that" come back garbled, in a language the
user reads and we do not, is a worse failure than any of the ones this table
costs us. Being data, it is also reviewable: a native speaker can correct a
row here without reading a line of Python.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Keys:
#   background   the answer is drawn from reference material, not from law
#   concept      a matched legal concept governs the question
#   provision    plain retrieval, no concept matched
#   quote_note   warns that the quoted statutory text below is in English
#   abstention   nothing in the corpus supports an answer
#   why          label introducing the reason for an abstention
#   page         cited page of a prose source
#   english_note shown when the paraphrase could not be localised
#
# {label} in `concept` is filled with the English concept label. It is left in
# English deliberately: it names a legal category ("Patentability of
# traditional knowledge"), and the terminology lock in core.language forbids
# machine-translating those.
# ---------------------------------------------------------------------------
STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "background": "Answering from the AYUSH reference material in the "
                      "corpus. This is background, not law:",
        "concept": "This is a question about {label}. The governing text says:",
        "provision": "The most relevant provision in the ingested corpus says:",
        "quote_note": "",
        "abstention": "I don't have authority in the ingested corpus to answer "
                      "that. Rather than assemble something plausible from "
                      "loosely related provisions, I'd rather say so.",
        "why": "Why",
        "page": "page",
        "offer": "If you tell me what's in your formulation, I can compile it "
                 "against this rule and show you findings for your "
                 "own facts.",
        "why_weak": "no provision in the corpus scored high enough to rely on",
        "why_gate": "the drafted answer could not be tied back to the retrieved "
                    "provisions, so it was withheld",
        "english_note": "",
    },
    "hi": {
        "background": "कॉर्पस की आयुष संदर्भ सामग्री से उत्तर दिया जा रहा है। "
                      "यह पृष्ठभूमि है, कानून नहीं:",
        "concept": "यह {label} से जुड़ा प्रश्न है। इसे नियंत्रित करने वाला "
                   "प्रावधान कहता है:",
        "provision": "कॉर्पस में सबसे प्रासंगिक प्रावधान कहता है:",
        "quote_note": "नीचे उद्धृत क़ानूनी पाठ क़ानून की मूल अंग्रेज़ी में है।",
        "abstention": "इस प्रश्न का उत्तर देने के लिए कॉर्पस में कोई प्राधिकार "
                      "नहीं है। ढीले-ढाले संबंधित प्रावधानों से कोई प्रशंसनीय "
                      "उत्तर गढ़ने के बजाय मैं यह कहना बेहतर समझता हूँ।",
        "why": "कारण",
        "page": "पृष्ठ",
        "offer": "अगर आप बताएँ कि आपके फ़ॉर्मुलेशन में क्या है, तो मैं उसे इस "
                 "प्रावधान के विरुद्ध compile करके आपके अपने तथ्यों पर "
                 "निष्कर्ष दिखा सकता हूँ।",
        "why_weak": "कॉर्पस में कोई प्रावधान इतना प्रासंगिक नहीं निकला कि उस पर "
                    "भरोसा किया जा सके",
        "why_gate": "तैयार किया गया उत्तर प्राप्त प्रावधानों से जोड़ा नहीं जा सका, "
                    "इसलिए उसे रोक दिया गया",
        "english_note": "व्याख्या अंग्रेज़ी में है: इस मशीन पर उपलब्ध मॉडल "
                        "भरोसेमंद हिन्दी नहीं लिख सका।",
    },
    "ta": {
        "background": "கார்பஸில் உள்ள ஆயுஷ் மேற்கோள் நூல்களிலிருந்து பதில் "
                      "அளிக்கப்படுகிறது. இது பின்னணித் தகவல், சட்டம் அல்ல:",
        "concept": "இது {label} தொடர்பான கேள்வி. அதை ஆளும் சட்டப் பிரிவு "
                   "கூறுவது:",
        "provision": "கார்பஸில் உள்ள மிகவும் பொருத்தமான சட்டப் பிரிவு கூறுவது:",
        "quote_note": "கீழே மேற்கோள் காட்டப்பட்டுள்ள சட்ட வாசகம் அதன் மூல "
                      "ஆங்கிலத்தில் உள்ளது.",
        "abstention": "இந்தக் கேள்விக்குப் பதிலளிக்கத் தேவையான சட்ட ஆதாரம் "
                      "கார்பஸில் இல்லை. தொடர்பற்ற பிரிவுகளிலிருந்து "
                      "நம்பத்தகுந்ததாகத் தோன்றும் ஒரு பதிலை உருவாக்குவதைவிட, "
                      "இதைச் சொல்வதே சரி.",
        "why": "காரணம்",
        "page": "பக்கம்",
        "offer": "உங்கள் தயாரிப்பில் என்ன உள்ளது என்று சொன்னால், அதை இந்தச் "
                 "சட்டப் பிரிவுக்கு எதிராக compile செய்து உங்கள் சொந்தத் "
                 "தகவல்களுக்கான முடிவுகளைக் காட்ட முடியும்.",
        "why_weak": "கார்பஸில் உள்ள எந்தச் சட்டப் பிரிவும் நம்பியிருக்கும் அளவுக்குப் "
                    "பொருத்தமாக இல்லை",
        "why_gate": "வரையப்பட்ட பதிலை மீட்டெடுக்கப்பட்ட சட்டப் பிரிவுகளுடன் இணைக்க "
                    "முடியவில்லை, எனவே அது வெளியிடப்படவில்லை",
        "english_note": "விளக்கம் ஆங்கிலத்தில் உள்ளது: இந்த இயந்திரத்தில் உள்ள "
                        "மாடலால் நம்பகமான தமிழில் எழுத முடியவில்லை.",
    },
    "te": {
        "background": "కార్పస్‌లోని ఆయుష్ సూచన సామగ్రి నుండి సమాధానం "
                      "ఇవ్వబడుతోంది. ఇది నేపథ్య సమాచారం, చట్టం కాదు:",
        "concept": "ఇది {label} గురించిన ప్రశ్న. దీన్ని నియంత్రించే నిబంధన "
                   "ఇలా చెబుతోంది:",
        "provision": "కార్పస్‌లో అత్యంత సంబంధిత నిబంధన ఇలా చెబుతోంది:",
        "quote_note": "క్రింద ఉదహరించిన చట్ట పాఠ్యం దాని మూల ఆంగ్లంలో ఉంది.",
        "abstention": "ఈ ప్రశ్నకు సమాధానం ఇవ్వడానికి కార్పస్‌లో ఆధారం లేదు. "
                      "సంబంధం లేని నిబంధనల నుండి నమ్మదగినట్లు కనిపించే "
                      "సమాధానాన్ని కూర్చడం కంటే ఇది చెప్పడమే మేలు.",
        "why": "కారణం",
        "page": "పేజీ",
        "offer": "మీ ఫార్ములేషన్‌లో ఏమి ఉందో చెబితే, దాన్ని ఈ నిబంధనకు "
                 "వ్యతిరేకంగా compile చేసి మీ స్వంత వాస్తవాలపై ఫలితాలు "
                 "చూపగలను.",
        "why_weak": "కార్పస్‌లోని ఏ నిబంధనా ఆధారపడేంత సంబంధితంగా లేదు",
        "why_gate": "రూపొందించిన సమాధానాన్ని తీసుకువచ్చిన నిబంధనలతో ముడిపెట్టలేకపోయాం, "
                    "కాబట్టి దాన్ని విడుదల చేయలేదు",
        "english_note": "వివరణ ఆంగ్లంలో ఉంది: ఈ మెషీన్‌లోని మోడల్ నమ్మదగిన "
                        "తెలుగు రాయలేకపోయింది.",
    },
    "kn": {
        "background": "ಕಾರ್ಪಸ್‌ನಲ್ಲಿರುವ ಆಯುಷ್ ಉಲ್ಲೇಖ ಸಾಮಗ್ರಿಯಿಂದ ಉತ್ತರಿಸಲಾಗುತ್ತಿದೆ. "
                      "ಇದು ಹಿನ್ನೆಲೆ ಮಾಹಿತಿ, ಕಾನೂನಲ್ಲ:",
        "concept": "ಇದು {label} ಕುರಿತ ಪ್ರಶ್ನೆ. ಅದನ್ನು ನಿಯಂತ್ರಿಸುವ ಉಪಬಂಧ ಹೀಗೆ "
                   "ಹೇಳುತ್ತದೆ:",
        "provision": "ಕಾರ್ಪಸ್‌ನಲ್ಲಿನ ಅತ್ಯಂತ ಸಂಬಂಧಿತ ಉಪಬಂಧ ಹೀಗೆ ಹೇಳುತ್ತದೆ:",
        "quote_note": "ಕೆಳಗೆ ಉಲ್ಲೇಖಿಸಿದ ಕಾನೂನು ಪಠ್ಯ ಅದರ ಮೂಲ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿದೆ.",
        "abstention": "ಈ ಪ್ರಶ್ನೆಗೆ ಉತ್ತರಿಸಲು ಕಾರ್ಪಸ್‌ನಲ್ಲಿ ಆಧಾರವಿಲ್ಲ. ಸಡಿಲವಾಗಿ "
                      "ಸಂಬಂಧಿಸಿದ ಉಪಬಂಧಗಳಿಂದ ನಂಬಲರ್ಹವೆನಿಸುವ ಉತ್ತರವನ್ನು "
                      "ಜೋಡಿಸುವುದಕ್ಕಿಂತ ಹೀಗೆ ಹೇಳುವುದೇ ಸರಿ.",
        "why": "ಕಾರಣ",
        "page": "ಪುಟ",
        "offer": "ನಿಮ್ಮ ಫಾರ್ಮುಲೇಶನ್‌ನಲ್ಲಿ ಏನಿದೆ ಎಂದು ಹೇಳಿದರೆ, ಅದನ್ನು ಈ ಉಪಬಂಧಕ್ಕೆ "
                 "ವಿರುದ್ಧವಾಗಿ compile ಮಾಡಿ ನಿಮ್ಮ ಸ್ವಂತ ಸಂಗತಿಗಳ ಮೇಲಿನ "
                 "ಫಲಿತಾಂಶಗಳನ್ನು ತೋರಿಸಬಲ್ಲೆ.",
        "why_weak": "ಕಾರ್ಪಸ್‌ನಲ್ಲಿನ ಯಾವ ಉಪಬಂಧವೂ ಅವಲಂಬಿಸುವಷ್ಟು ಸಂಬಂಧಿತವಾಗಿಲ್ಲ",
        "why_gate": "ರಚಿಸಿದ ಉತ್ತರವನ್ನು ಪಡೆದ ಉಪಬಂಧಗಳಿಗೆ ಜೋಡಿಸಲಾಗಲಿಲ್ಲ, ಆದ್ದರಿಂದ ಅದನ್ನು "
                    "ತಡೆಹಿಡಿಯಲಾಯಿತು",
        "english_note": "ವಿವರಣೆ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿದೆ: ಈ ಯಂತ್ರದಲ್ಲಿನ ಮಾದರಿಗೆ "
                        "ನಂಬಲರ್ಹ ಕನ್ನಡ ಬರೆಯಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ.",
    },
    "ml": {
        "background": "കോർപ്പസിലെ ആയുഷ് റഫറൻസ് സാമഗ്രിയിൽ നിന്നാണ് ഉത്തരം. "
                      "ഇത് പശ്ചാത്തല വിവരമാണ്, നിയമമല്ല:",
        "concept": "ഇത് {label} സംബന്ധിച്ച ചോദ്യമാണ്. അതിനെ നിയന്ത്രിക്കുന്ന "
                   "വ്യവസ്ഥ പറയുന്നത്:",
        "provision": "കോർപ്പസിലെ ഏറ്റവും പ്രസക്തമായ വ്യവസ്ഥ പറയുന്നത്:",
        "quote_note": "താഴെ ഉദ്ധരിച്ച നിയമ വാചകം അതിന്റെ മൂല ഇംഗ്ലീഷിലാണ്.",
        "abstention": "ഈ ചോദ്യത്തിന് ഉത്തരം നൽകാൻ കോർപ്പസിൽ ആധികാരികതയില്ല. "
                      "അയഞ്ഞ ബന്ധമുള്ള വ്യവസ്ഥകളിൽ നിന്ന് വിശ്വസനീയമെന്ന് "
                      "തോന്നുന്ന ഒരു ഉത്തരം ഉണ്ടാക്കുന്നതിനേക്കാൾ ഇത് "
                      "പറയുന്നതാണ് ശരി.",
        "why": "കാരണം",
        "page": "പേജ്",
        "offer": "നിങ്ങളുടെ ഫോർമുലേഷനിൽ എന്താണുള്ളതെന്ന് പറഞ്ഞാൽ, അത് ഈ "
                 "വ്യവസ്ഥയ്ക്കെതിരെ compile ചെയ്ത് നിങ്ങളുടെ സ്വന്തം "
                 "വസ്തുതകളുടെ അടിസ്ഥാനത്തിലുള്ള കണ്ടെത്തലുകൾ കാണിക്കാം.",
        "why_weak": "കോർപ്പസിലെ ഒരു വ്യവസ്ഥയും ആശ്രയിക്കാവുന്നത്ര പ്രസക്തമായിരുന്നില്ല",
        "why_gate": "തയ്യാറാക്കിയ ഉത്തരം കണ്ടെടുത്ത വ്യവസ്ഥകളുമായി ബന്ധിപ്പിക്കാനായില്ല, "
                    "അതിനാൽ അത് തടഞ്ഞുവച്ചു",
        "english_note": "വിശദീകരണം ഇംഗ്ലീഷിലാണ്: ഈ യന്ത്രത്തിലെ മോഡലിന് "
                        "വിശ്വസനീയമായ മലയാളം എഴുതാൻ കഴിഞ്ഞില്ല.",
    },
    "bn": {
        "background": "কর্পাসে থাকা আয়ুষ তথ্যসূত্র থেকে উত্তর দেওয়া হচ্ছে। "
                      "এটি পটভূমি, আইন নয়:",
        "concept": "এটি {label} সংক্রান্ত প্রশ্ন। এটি নিয়ন্ত্রণকারী বিধান বলছে:",
        "provision": "কর্পাসে সবচেয়ে প্রাসঙ্গিক বিধান বলছে:",
        "quote_note": "নীচে উদ্ধৃত আইনি পাঠ্যটি তার মূল ইংরেজিতে রয়েছে।",
        "abstention": "এই প্রশ্নের উত্তর দেওয়ার মতো কোনো কর্তৃত্ব কর্পাসে নেই। "
                      "আলগাভাবে সম্পর্কিত বিধান থেকে বিশ্বাসযোগ্য মনে হয় এমন "
                      "উত্তর সাজানোর চেয়ে এটি বলাই ভালো।",
        "why": "কারণ",
        "page": "পৃষ্ঠা",
        "offer": "আপনার ফর্মুলেশনে কী আছে জানালে, আমি সেটিকে এই বিধানের "
                 "বিপরীতে compile করে আপনার নিজের তথ্যের ভিত্তিতে ফলাফল "
                 "দেখাতে পারি।",
        "why_weak": "কর্পাসের কোনো বিধানই নির্ভর করার মতো যথেষ্ট প্রাসঙ্গিক নয়",
        "why_gate": "খসড়া উত্তরটি পুনরুদ্ধার করা বিধানগুলির সঙ্গে মেলানো যায়নি, তাই "
                    "সেটি প্রকাশ করা হয়নি",
        "english_note": "ব্যাখ্যাটি ইংরেজিতে: এই মেশিনের মডেল নির্ভরযোগ্য "
                        "বাংলা লিখতে পারেনি।",
    },
    "gu": {
        "background": "કોર્પસમાંની આયુષ સંદર્ભ સામગ્રીમાંથી જવાબ આપવામાં આવે છે. "
                      "આ પૃષ્ઠભૂમિ છે, કાયદો નથી:",
        "concept": "આ {label} અંગેનો પ્રશ્ન છે. તેને નિયંત્રિત કરતી જોગવાઈ કહે છે:",
        "provision": "કોર્પસમાં સૌથી સુસંગત જોગવાઈ કહે છે:",
        "quote_note": "નીચે ટાંકેલું કાનૂની લખાણ તેની મૂળ અંગ્રેજીમાં છે.",
        "abstention": "આ પ્રશ્નનો જવાબ આપવા માટે કોર્પસમાં કોઈ આધાર નથી. છૂટક "
                      "રીતે સંબંધિત જોગવાઈઓમાંથી બુદ્ધિગમ્ય લાગતો જવાબ ઘડવા "
                      "કરતાં આ કહેવું વધુ યોગ્ય છે.",
        "why": "કારણ",
        "page": "પાનું",
        "offer": "તમારા ફોર્મ્યુલેશનમાં શું છે તે જણાવો, તો હું તેને આ જોગવાઈ "
                 "સામે compile કરીને તમારા પોતાના તથ્યો પર તારણો બતાવી "
                 "શકું.",
        "why_weak": "કોર્પસમાંની કોઈ જોગવાઈ ભરોસો કરવા જેટલી સુસંગત નથી",
        "why_gate": "તૈયાર કરેલો જવાબ મેળવેલી જોગવાઈઓ સાથે જોડી શકાયો નહીં, તેથી તેને "
                    "રોકી રાખવામાં આવ્યો",
        "english_note": "સમજૂતી અંગ્રેજીમાં છે: આ મશીન પરનું મોડેલ ભરોસાપાત્ર "
                        "ગુજરાતી લખી શક્યું નહીં.",
    },
    "pa": {
        "background": "ਕਾਰਪਸ ਵਿੱਚ ਮੌਜੂਦ ਆਯੁਸ਼ ਹਵਾਲਾ ਸਮੱਗਰੀ ਤੋਂ ਜਵਾਬ ਦਿੱਤਾ ਜਾ ਰਿਹਾ "
                      "ਹੈ। ਇਹ ਪਿਛੋਕੜ ਹੈ, ਕਾਨੂੰਨ ਨਹੀਂ:",
        "concept": "ਇਹ {label} ਬਾਰੇ ਸਵਾਲ ਹੈ। ਇਸ ਨੂੰ ਨਿਯੰਤਰਿਤ ਕਰਨ ਵਾਲੀ ਵਿਵਸਥਾ "
                   "ਕਹਿੰਦੀ ਹੈ:",
        "provision": "ਕਾਰਪਸ ਵਿੱਚ ਸਭ ਤੋਂ ਢੁਕਵੀਂ ਵਿਵਸਥਾ ਕਹਿੰਦੀ ਹੈ:",
        "quote_note": "ਹੇਠਾਂ ਦਿੱਤਾ ਕਾਨੂੰਨੀ ਪਾਠ ਇਸਦੀ ਮੂਲ ਅੰਗਰੇਜ਼ੀ ਵਿੱਚ ਹੈ।",
        "abstention": "ਇਸ ਸਵਾਲ ਦਾ ਜਵਾਬ ਦੇਣ ਲਈ ਕਾਰਪਸ ਵਿੱਚ ਕੋਈ ਆਧਾਰ ਨਹੀਂ ਹੈ। "
                      "ਢਿੱਲੇ ਤੌਰ ਉੱਤੇ ਸਬੰਧਤ ਵਿਵਸਥਾਵਾਂ ਤੋਂ ਕੋਈ ਭਰੋਸੇਯੋਗ ਲੱਗਣ "
                      "ਵਾਲਾ ਜਵਾਬ ਘੜਨ ਨਾਲੋਂ ਇਹ ਕਹਿਣਾ ਬਿਹਤਰ ਹੈ।",
        "why": "ਕਾਰਨ",
        "page": "ਪੰਨਾ",
        "offer": "ਜੇ ਤੁਸੀਂ ਦੱਸੋ ਕਿ ਤੁਹਾਡੇ ਫਾਰਮੂਲੇਸ਼ਨ ਵਿੱਚ ਕੀ ਹੈ, ਤਾਂ ਮੈਂ ਉਸਨੂੰ ਇਸ "
                 "ਵਿਵਸਥਾ ਦੇ ਵਿਰੁੱਧ compile ਕਰਕੇ ਤੁਹਾਡੇ ਆਪਣੇ ਤੱਥਾਂ ਉੱਤੇ "
                 "ਨਤੀਜੇ ਦਿਖਾ ਸਕਦਾ ਹਾਂ।",
        "why_weak": "ਕਾਰਪਸ ਵਿੱਚ ਕੋਈ ਵੀ ਵਿਵਸਥਾ ਭਰੋਸਾ ਕਰਨ ਜੋਗੀ ਢੁਕਵੀਂ ਨਹੀਂ ਨਿਕਲੀ",
        "why_gate": "ਤਿਆਰ ਕੀਤਾ ਜਵਾਬ ਲੱਭੀਆਂ ਵਿਵਸਥਾਵਾਂ ਨਾਲ ਜੋੜਿਆ ਨਹੀਂ ਜਾ ਸਕਿਆ, ਇਸ ਲਈ "
                    "ਉਸਨੂੰ ਰੋਕ ਦਿੱਤਾ ਗਿਆ",
        "english_note": "ਵਿਆਖਿਆ ਅੰਗਰੇਜ਼ੀ ਵਿੱਚ ਹੈ: ਇਸ ਮਸ਼ੀਨ ਦਾ ਮਾਡਲ ਭਰੋਸੇਯੋਗ "
                        "ਪੰਜਾਬੀ ਨਹੀਂ ਲਿਖ ਸਕਿਆ।",
    },
    "or": {
        "background": "କର୍ପସରେ ଥିବା ଆୟୁଷ ସନ୍ଦର୍ଭ ସାମଗ୍ରୀରୁ ଉତ୍ତର ଦିଆଯାଉଛି। ଏହା "
                      "ପୃଷ୍ଠଭୂମି, ଆଇନ ନୁହେଁ:",
        "concept": "ଏହା {label} ସମ୍ବନ୍ଧୀୟ ପ୍ରଶ୍ନ। ଏହାକୁ ନିୟନ୍ତ୍ରଣ କରୁଥିବା ବ୍ୟବସ୍ଥା "
                   "କହେ:",
        "provision": "କର୍ପସରେ ସବୁଠାରୁ ପ୍ରାସଙ୍ଗିକ ବ୍ୟବସ୍ଥା କହେ:",
        "quote_note": "ତଳେ ଉଦ୍ଧୃତ ଆଇନଗତ ପାଠ ଏହାର ମୂଳ ଇଂରାଜୀରେ ଅଛି।",
        "abstention": "ଏହି ପ୍ରଶ୍ନର ଉତ୍ତର ଦେବା ପାଇଁ କର୍ପସରେ କୌଣସି ଆଧାର ନାହିଁ। "
                      "ଢିଲା ଭାବେ ସମ୍ପର୍କିତ ବ୍ୟବସ୍ଥାରୁ ବିଶ୍ୱାସଯୋଗ୍ୟ ଦେଖାଯାଉଥିବା "
                      "ଉତ୍ତର ଗଢ଼ିବା ଅପେକ୍ଷା ଏହା କହିବା ଭଲ।",
        "why": "କାରଣ",
        "page": "ପୃଷ୍ଠା",
        "offer": "ଆପଣଙ୍କ ଫର୍ମୁଲେସନରେ କଣ ଅଛି ଜଣାଇଲେ, ମୁଁ ତାହାକୁ ଏହି ବ୍ୟବସ୍ଥା "
                 "ବିରୁଦ୍ଧରେ compile କରି ଆପଣଙ୍କ ନିଜ ତଥ୍ୟ ଉପରେ ଫଳାଫଳ "
                 "ଦେଖାଇ ପାରିବି।",
        "why_weak": "କର୍ପସର କୌଣସି ବ୍ୟବସ୍ଥା ନିର୍ଭର କରିବା ପାଇଁ ଯଥେଷ୍ଟ ପ୍ରାସଙ୍ଗିକ ନୁହେଁ",
        "why_gate": "ପ୍ରସ୍ତୁତ ଉତ୍ତରକୁ ମିଳିଥିବା ବ୍ୟବସ୍ଥା ସହ ଯୋଡ଼ି ହେଲା ନାହିଁ, ତେଣୁ ତାହା "
                    "ପ୍ରକାଶ କରାଯାଇ ନାହିଁ",
        "english_note": "ବ୍ୟାଖ୍ୟା ଇଂରାଜୀରେ ଅଛି: ଏହି ମେସିନର ମଡେଲ ବିଶ୍ୱାସଯୋଗ୍ୟ "
                        "ଓଡ଼ିଆ ଲେଖି ପାରିଲା ନାହିଁ।",
    },
    "ur": {
        "background": "کارپس میں موجود آیوش حوالہ جاتی مواد سے جواب دیا جا رہا "
                      "ہے۔ یہ پس منظر ہے، قانون نہیں:",
        "concept": "یہ {label} سے متعلق سوال ہے۔ اس پر لاگو ہونے والی دفعہ "
                   "کہتی ہے:",
        "provision": "کارپس میں سب سے متعلقہ دفعہ کہتی ہے:",
        "quote_note": "نیچے نقل کیا گیا قانونی متن اپنی اصل انگریزی میں ہے۔",
        "abstention": "اس سوال کا جواب دینے کے لیے کارپس میں کوئی سند موجود "
                      "نہیں۔ ڈھیلے طور پر متعلقہ دفعات سے کوئی قابلِ اعتبار "
                      "نظر آنے والا جواب گھڑنے کے بجائے یہ کہنا بہتر ہے۔",
        "why": "وجہ",
        "page": "صفحہ",
        "offer": "اگر آپ بتائیں کہ آپ کے فارمولیشن میں کیا ہے، تو میں اسے اس "
                 "دفعہ کے مقابلے میں compile کر کے آپ کے اپنے حقائق پر "
                 "نتائج دکھا سکتا ہوں۔",
        "why_weak": "کارپس میں کوئی دفعہ اتنی متعلقہ نہیں نکلی کہ اس پر بھروسہ کیا جا سکے",
        "why_gate": "تیار کیا گیا جواب حاصل کردہ دفعات سے جوڑا نہ جا سکا، اس لیے اسے "
                    "روک لیا گیا",
        "english_note": "وضاحت انگریزی میں ہے: اس مشین کا ماڈل قابلِ اعتماد "
                        "اردو نہیں لکھ سکا۔",
    },
}


# Sentence terminator. The North Indian scripts end a sentence with the danda,
# Urdu with the Arabic full stop; the South Indian scripts adopted the Latin
# period. Ending a Hindi sentence with "." is the kind of small wrongness that
# tells a reader the text was assembled by something that does not read Hindi.
STOP = {
    "hi": "।", "bn": "।", "pa": "।", "gu": "।", "or": "।",
    "ur": "۔",
}


def full_stop(code: str) -> str:
    return STOP.get(code, ".")


def t(code: str, key: str, **fmt) -> str:
    """Look up a scaffolding string, falling back to English.

    Falling back rather than raising is deliberate: a language we have no row
    for should degrade to an English answer that is still correct, not to a
    KeyError in front of a user.
    """
    row = STRINGS.get(code) or STRINGS["en"]
    s = row.get(key) or STRINGS["en"].get(key, "")
    return s.format(**fmt) if fmt else s



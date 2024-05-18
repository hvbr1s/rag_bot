from semantic_router import Route

chitchat = Route(
    name="chitchat",
    utterances=[
        "hello",
        "hi",
        "bonjour",
        "salut",
        "how are you?",
        "Привет",
        "Здравствуйте",
        "Добрый день",
        "hdkfebkejb",
        "null", 
        "I have a question",
    ],
)
human = Route(
    name="human",
    utterances=[
        "agent",
        "agente",
        "representative",
        "speak to human",
        "talk to agent",
        "transfer to operator",
        "I want to speak to a person",
        "support",
        "human",
        "operator",
        "live support",
        "live chat",
        "147999 Issue",
        "Case ID 8888888",
        "submit new ticket",
        "I need a new ticket for my running case. Its unfortunately closed."

    ],
)

niceties = Route(
    name="niceties",
    utterances=[
        "thanks!",
        "thank you very much",
        "merci!",
        "Super, merci!",
        "Спасибо",
        "Благодарю",
        "human",
        "Спасибо большое",
        "okay",
        "ok ok",

    ],
)

languages = Route(
    name="languages",
    utterances=[
        "Can I input text in Russian language?",
        "Can I write Russian?",
        "Sprechen sie deutsch?",
        "Do you speak German?",
        "Do you speak Russian?",
        "Do you speak Spanish?",
        "Est-ce que je peux poser ma question en Francais?",
        "вы говорите по-русски?",
        "Türkçe konuşuyor musunuz?",
        "Türkçe biliyor musunuz?",
        "你会说土耳其语吗?",

    ],
)

phone = Route(
    name="phone",
    utterances=[
        "phone support",
        "do you have phone support?",
        "phone"
    ],
)

ROUTER_DICTIONARY = {

        "chitchat": {
            "eng": "Hello! How can I assist you today? Please describe your issue in as much detail as possible, including your Ledger device model (Nano S, Nano X, or Nano S Plus), any error messages you're encountering, and the type of crypto (e.g., Bitcoin, Ethereum, Solana, XRP, or another).",
            "fr": "Bonjour ! Comment puis-je vous aider aujourd'hui ? Veuillez décrire votre problème avec autant de détails que possible, y compris le modèle de votre appareil Ledger (Nano S, Nano X ou Nano S Plus), tous les messages d'erreur que vous rencontrez et le type de crypto-monnaie (par exemple, Bitcoin, Ethereum, Solana, XRP ou autre).",
            "ru": "Привет! Как я могу помочь вам сегодня? Пожалуйста, опишите свою проблему как можно подробнее, включая модель вашего устройства Ledger (Nano S, Nano X или Nano S Plus), любые сообщения об ошибках, с которыми вы столкнулись, и тип криптовалюты (например, Bitcoin, Ethereum, Solana, XRP или другую).",
            "es": "¡Hola! ¿Cómo puedo ayudarte hoy? Por favor, describe tu problema con la mayor cantidad de detalles posible, incluyendo el modelo de tu dispositivo Ledger (Nano S, Nano X o Nano S Plus), cualquier mensaje de error que estés recibiendo y el tipo de criptomoneda (por ejemplo, Bitcoin, Ethereum, Solana, XRP u otra)"
        },

        "human": {
            "eng": "Hello! To speak with a human agent, please click the 'I have followed the instructions, still require assistance' button for further help.",
            "fr": "Bonjour! Pour parler à un agent humain, veuillez cliquer sur le bouton 'Parler à un agent' pour obtenir de l'aide.",
            "ru": "Привет! Чтобы поговорить с агентом техподдержки, пожалуйста, нажмите кнопку ‘Говорить с агентом’ для получения помощи.",
            "es": "¡Hola! Para hablar con un agente humano, por favor haz clic en el botón 'Hablar con un agente' para recibir ayuda."
        },

        "niceties": {
            "eng": "You're welcome! If you have any more questions about cryptocurrencies, or how to use your Ledger device, don't hesitate to ask!",
            "fr": "De rien ! Si vous avez d'autres questions sur les cryptomonnaies ou sur l'utilisation de votre appareil Ledger, n'hésitez pas à demander!",
            "ru": "Пожалуйста! Если у вас остались вопросы о криптовалюте или о том, как использовать ваше устройство Ledger, не стесняйтесь их задавать!",
            "es": "¡De nada! Si tienes más preguntas sobre criptomonedas o cómo usar tu dispositivo Ledger, ¡no dudes en preguntar!"
        },

        "languages": {
            "eng": "Hello! As an AI assistant, I can understand several languages but I can respond only in English, French, Spanish or Russian. However, feel free to ask your question in the language you're most comfortable with. Please describe your issue in as much detail as possible, including your Ledger device model (Nano S, Nano X, or Nano S Plus), any error messages you're encountering, and the type of crypto (e.g., Bitcoin, Ethereum, Solana, XRP, or another).",
            "fr": "Bonjour! Oui je parle français. Comment puis-je vous aider aujourd'hui ? Veuillez décrire votre problème avec autant de détails que possible, y compris le modèle de votre appareil Ledger (Nano S, Nano X ou Nano S Plus), tous les messages d'erreur que vous rencontrez et le type de crypto-monnaie (par exemple, Bitcoin, Ethereum, Solana, XRP ou autre).",
            "ru": "Здравствуйте! Да, я говорю по-русски. Как я могу помочь вам сегодня? Пожалуйста, опишите свою проблему как можно подробнее, включая модель вашего устройства Ledger (Nano S, Nano X или Nano S Plus), любые сообщения об ошибках, с которыми вы столкнулись, и тип криптовалюты (например, Bitcoin, Ethereum, Solana, XRP или другую).",
            "es": "¡Hola! Sí, hablo español. ¿Cómo puedo ayudarte hoy? Por favor, describe tu problema con el mayor detalle posible, incluyendo el modelo de tu dispositivo Ledger (Nano S, Nano X o Nano S Plus), cualquier mensaje de error que estés encontrando y el tipo de criptomoneda (por ejemplo, Bitcoin, Ethereum, Solana, XRP u otra)."
        },
        "phone":{
            "eng":"Hi there, Ledger does not offer phone support. If someone called you claiming to be from Ledger, it's a scam. Do not engage or share any information. If you wish to speak with a human agent, please click the 'I have followed the instructions, still require assistance' button for further help.",
            "fr":"Bonjour, Ledger n'offre pas de support téléphonique. Si quelqu'un vous a appelé en prétendant être de chez Ledger, c'est une arnaque. Raccrochez tout de suite et ne partagez aucune information. Si vous souhaitez parler à un agent humain, veuillez cliquer sur le bouton 'Parler à un agent' pour obtenir de l'aide.",
            "ru":"дравствуйте, компания Ledger не предоставляет поддержку по телефону. Если вам позвонил человек, утверждающий, что он из Ledger, это мошенничество. Не вступайте в контакт и не сообщайте никакой информации. Если вы хотите поговорить с человеком, пожалуйста, нажмите кнопку 'Поговорить с агентом” для получения дальнейшей помощи.'",
            "es": "¡Hola! Ledger no ofrece soporte telefónico. Si alguien te llamó afirmando ser de Ledger, es una estafa. No te involucres ni compartas ninguna información. Si deseas hablar con un agente humano, por favor haz clic en el botón 'Hablar con un agente' para recibir ayuda adicional."
        }

}

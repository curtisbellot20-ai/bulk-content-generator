import anthropic

CONTENT_PROMPTS = {
    "blog_post": (
        "Write a well-structured blog post about: {topic}.\n"
        "Include an engaging introduction, 3-5 main sections with subheadings, and a conclusion.\n"
        "Tone: {tone}. Length: approximately 500-700 words."
    ),
    "social_media": (
        "Write 3 social media posts (for LinkedIn, Twitter/X, and Instagram) about: {topic}.\n"
        "Each post should be platform-appropriate in length and style.\n"
        "Tone: {tone}. Include relevant hashtags for Instagram."
    ),
    "product_description": (
        "Write a compelling product description for: {topic}.\n"
        "Include key features, benefits, and a call to action.\n"
        "Tone: {tone}. Length: 150-250 words."
    ),
    "email": (
        "Write a professional email about: {topic}.\n"
        "Include subject line, greeting, body, and sign-off.\n"
        "Tone: {tone}."
    ),
    "ad_copy": (
        "Write compelling advertising copy for: {topic}.\n"
        "Include a headline, subheadline, body copy, and call to action.\n"
        "Tone: {tone}. Keep it punchy and persuasive."
    ),
    "seo_article": (
        "Write an SEO-optimized article about: {topic}.\n"
        "Naturally incorporate the main keyword throughout. Include a meta description at the top.\n"
        "Tone: {tone}. Length: approximately 800-1000 words."
    ),
}

DEFAULT_PROMPT = (
    "Write high-quality content about: {topic}.\n"
    "Tone: {tone}."
)


def generate_content(topic: str, content_type: str = "blog_post", tone: str = "professional") -> str:
    client = anthropic.Anthropic()
    prompt_template = CONTENT_PROMPTS.get(content_type, DEFAULT_PROMPT)
    prompt = prompt_template.format(topic=topic, tone=tone)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text

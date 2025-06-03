import fitz  # PyMuPDF
import re
import anthropic


def extract_text_for_gpt(pdf_path):
    doc = fitz.open(pdf_path)
    text = ''.join(page.get_text() for page in doc)

    # 한글은 제거하고, 숫자/기호 일부는 유지할 수도 있음
    text = re.sub(r'[가-힣]', ' ', text)  # 공백으로 바꾸는 게 안전

    # 공백 정리
    text = re.sub(r'\s+', ' ', text).strip()

    return text

def ask_gpt_to_extract_hanja(text):
    client = anthropic.Anthropic(
        api_key="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"
    )

    prompt = f"""
    다음 텍스트에서 한자 문장이랑 2글자 이상 한자 글자를 추출해주세요.
    중복 없이 정리해주세요. 줄 단위로 출력해주세요.
    {text}
    """

    message = client.messages.create(
        model="claude-opus-4-20250514",
        max_tokens=1024,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return message.content[0].text


if __name__ == "__main__":
    pdf_path = r"Z:\pdf_hanja_server\uploads\276d1863-699e-420f-95bc-a86c8dcdca54.pdf"  # 실제 경로로 대체
    text = extract_text_for_gpt(pdf_path)
    print(text)
    result = ask_gpt_to_extract_hanja(text)

    print(result)

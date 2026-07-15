from pathlib import Path

app_code = r'''import logging
import os

from flask import Flask, abort, request
from openai import OpenAI
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent


# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# RenderのEnvironment Variablesから秘密情報を読み込む
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

missing_variables = [
    name
    for name, value in {
        "LINE_CHANNEL_ACCESS_TOKEN": LINE_CHANNEL_ACCESS_TOKEN,
        "LINE_CHANNEL_SECRET": LINE_CHANNEL_SECRET,
        "OPENAI_API_KEY": OPENAI_API_KEY,
    }.items()
    if not value
]

if missing_variables:
    raise RuntimeError(
        "次の環境変数が設定されていません: " + ", ".join(missing_variables)
    )

# 各サービスの初期設定
app = Flask(__name__)
openai_client = OpenAI(api_key=OPENAI_API_KEY)
line_configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)


SYSTEM_INSTRUCTIONS = """
あなたは兵庫県明石市の「鍼灸接骨院Life」のLINE問い合わせ対応AIです。
患者さんに対して、丁寧で親しみやすい日本語で簡潔に回答してください。

必ず守ること:
- 医師の診断の代わりになる断定や、病名の確定をしない。
- 緊急性が疑われる症状には、119番、救急相談、医療機関への受診を案内する。
- 強い胸痛、呼吸困難、意識障害、ろれつが回らない、片側の麻痺、
  激しい頭痛、大量出血などがある場合は、すぐに救急要請を勧める。
- 料金、営業時間、定休日、予約状況など、登録されていない情報を推測しない。
- 分からない情報は「スタッフが確認します」と案内する。
- 個人情報、保険証情報、クレジットカード情報などをLINE上で送らせない。
- 返信は原則として400文字以内にする。
- 最後に必要に応じて、予約またはスタッフへの確認を自然に案内する。

現時点で案内できる内容:
- 接骨・鍼灸・身体の相談に対応している。
- 交通事故後の施術相談を受け付けている。
- 詳細な料金、営業時間、空き状況はスタッフ確認が必要。
"""


@app.get("/")
def home():
    """Renderの稼働確認用ページ。"""
    return "鍼灸接骨院Life AIチャットボットは正常に稼働しています。", 200


@app.post("/callback")
def callback():
    """LINEから届いたWebhookを受け取る入口。"""
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    if not signature:
        logger.warning("X-Line-Signatureがありません。")
        abort(400)

    try:
        # LINE公式SDKで署名を検証してからイベントを処理
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("LINEの署名検証に失敗しました。")
        abort(400)
    except Exception:
        logger.exception("Webhook処理中に予期しないエラーが発生しました。")
        abort(500)

    return "OK", 200


@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    """ユーザーの文字メッセージをOpenAIへ送り、LINEへ返信する。"""
    user_message = (event.message.text or "").strip()

    if not user_message:
        reply_text = "メッセージを入力してください。"
    else:
        try:
            response = openai_client.responses.create(
                model=OPENAI_MODEL,
                instructions=SYSTEM_INSTRUCTIONS,
                input=user_message,
                max_output_tokens=500,
            )
            reply_text = (response.output_text or "").strip()

            if not reply_text:
                reply_text = (
                    "うまく回答を作成できませんでした。"
                    "恐れ入りますが、もう一度送信してください。"
                )
        except Exception:
            logger.exception("OpenAI APIの呼び出しに失敗しました。")
            reply_text = (
                "ただいまAIの応答に時間がかかっています。"
                "恐れ入りますが、少し時間を空けてもう一度お試しください。"
            )

    # LINEの文字数上限に余裕を持たせる
    reply_text = reply_text[:4500]

    try:
        with ApiClient(line_configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply_text)],
                )
            )
    except Exception:
        logger.exception("LINEへの返信に失敗しました。")


if __name__ == "__main__":
    # Renderではgunicornを使うため、ここはローカル確認用
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
'''

path = Path("/mnt/data/app.py")
path.write_text(app_code, encoding="utf-8")
print(f"作成しました: {path}")
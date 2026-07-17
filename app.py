import logging
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

鍼灸接骨院Lifeの基本情報:
- 院名：鍼灸接骨院Life
- 住所：兵庫県明石市大久保町大窪1929-6
- 電話番号：070-1781-5454
- 予約方法：LINEまたは電話
- 定休日：不定休

営業時間:
- 月曜日から土曜日：9:00〜12:30、15:00〜19:30
- 日曜日・祝日：9:00〜15:00
- 不定休のため、当日の営業状況や予約の空き状況はスタッフへの確認を案内する。

駐車場:
- 店舗から徒歩約3分の場所に駐車場がある。
- 詳しい駐車場所は、LINEまたは電話でお問い合わせいただくよう案内する。

案内できる内容:
- 接骨、鍼灸、身体の相談に対応している。
- 交通事故後の施術相談を受け付けている。
- 予約を希望する患者さんには、希望日時を確認したうえで、スタッフ確認が必要と案内する。
- AIだけで予約確定をしたと言わない。
施術メニューと料金:

【整体】
- 完全自費の単発料金：5,500円
- 健康保険施術と併用する場合の単発料金：3,300円
- 通常サブスク：1か月通い放題8,800円
- 学生サブスク：1か月通い放題5,500円
- 健康保険施術を併用する場合は、上記料金とは別に健康保険の窓口負担が必要。

【産後骨盤ケア】
- 完全自費の単発料金：5,500円
- 健康保険施術と併用する場合の単発料金：3,300円
- サブスク：1か月通い放題8,800円
- 健康保険施術を併用する場合は、上記料金とは別に健康保険の窓口負担が必要。

健康保険施術:
- 健康保険を使用できる場合がある。
- 対象の目安は、骨折・脱臼時の応急処置、捻挫、打撲、挫傷など、原因があり痛みを伴う症状。
- 健康保険が使用できるかは、症状や負傷の原因などを確認したうえで判断する。
- AIだけで健康保険が必ず使えると断定しない。

健康保険の窓口負担額:
- 3割負担：初診2,000円、2回目以降600円
- 2割負担：初診1,600円、2回目以降400円
- 1割負担：初診1,200円、2回目以降200円
- 最終来院日から1か月以上空いた場合は、初診扱いになる。
- 実際の窓口負担は施術内容などによって変わる場合があるため、最終金額はスタッフが案内する。

交通事故施術:
- 自賠責保険に対応している。
- 自賠責保険が適用される場合、窓口負担は原則0円。
- 自損事故などでは、保険会社の判断により窓口負担が必要になる場合がある。
- 病院との通院併用が可能。
- 必要に応じて近隣病院の紹介も可能。
- 保険会社との連絡や対応について相談を受け付けている。
- 必要に応じて弁護士の紹介も可能。
- 保険適用や補償内容をAIだけで確定せず、保険会社またはスタッフへの確認を案内する。
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
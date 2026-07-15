from flask import Flask, request

app = Flask(__name__)

@app.route("/")
def home():
    return "鍼灸接骨院Life AIチャットボットが起動しています！"

@app.route("/callback", methods=["POST"])
def callback():
    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
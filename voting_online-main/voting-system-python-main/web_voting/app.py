from flask import Flask, render_template, request, redirect, session, flash, jsonify, send_from_directory
from eth_account.messages import encode_defunct
from eth_account import Account
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "123456"

# Danh sách mã bầu cử hợp lệ
VALID_VOTE_CODES = {
    "VOTE2024": "Mã chung",
    "VOTE001": "Nhóm 1",
    "VOTE002": "Nhóm 2",
    "VOTE003": "Nhóm 3",
    "VOTE004": "Nhóm 4",
    "VOTE005": "Nhóm 5",
}

# Đường dẫn file CSV
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, "../database/cand_list.csv")
IMG_DIR = os.path.join(BASE_DIR, "../img")


# =========================
# Đọc danh sách ứng viên
# =========================
def get_candidates():
    df = pd.read_csv(FILE_PATH)
    return df


# =========================
# Phục vụ ảnh từ thư mục img
# =========================
@app.route('/img/<filename>')
def serve_img(filename):
    return send_from_directory(IMG_DIR, filename)


# =========================
# Trang đăng nhập
# =========================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        votecode = request.form.get("votecode", "").strip()
        username = request.form.get("username", "").strip()
        
        # Kiểm tra mã bầu cử
        if votecode not in VALID_VOTE_CODES:
            flash("❌ Mã bầu cử không hợp lệ!", "error")
            return render_template("login.html")
        
        if not username:
            flash("❌ Vui lòng nhập tên đăng nhập!", "error")
            return render_template("login.html")
        
        # Lưu vào session
        session["votecode"] = votecode
        session["user"] = username
        return redirect("/vote_page")
    return render_template("login.html")


# =========================
# Trang vote
# =========================
@app.route("/vote_page")
def vote_page():
    if "user" not in session:
        return redirect("/")

    df = get_candidates()
    return render_template("vote.html", candidates=df.to_dict(orient="records"))


# =========================
# Route vote (KHÔNG gọi blockchain nữa)
# =========================
@app.route("/vote", methods=["POST"])
def vote():
    name = request.form["candidate"]

    # Chỉ thông báo (vote thật xử lý bằng MetaMask JS)
    flash(f"🟡 Đã gửi yêu cầu vote cho {name} (xác nhận trên MetaMask)", "info")

    return redirect("/vote_page")


# =========================
# Trang kết quả
# =========================
@app.route("/result")
def result():
    df = get_candidates()

    # Hiện dữ liệu từ CSV (tạm thời)
    candidates = df.to_dict(orient="records")

    return render_template("result.html", candidates=candidates)


# =========================
# Đăng nhập bằng MetaMask
# =========================
@app.route('/login_wallet', methods=['POST'])
def login_wallet():
    data = request.get_json()

    address = data.get("address")
    signature = data.get("signature")
    message = data.get("message")

    try:
        # Xác minh chữ ký
        msg = encode_defunct(text=message)
        recovered_address = Account.recover_message(msg, signature=signature)

        # Kiểm tra xem địa chỉ khôi phục có khớp với địa chỉ gửi không
        if recovered_address.lower() == address.lower():
            session["user"] = address
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Chữ ký không hợp lệ"})

    except Exception as e:
        print("Lỗi verify:", e)
        return jsonify({"success": False, "error": str(e)})


# =========================
# Reset dữ liệu vote
# =========================
@app.route("/reset")
def reset():
    df = pd.read_csv(FILE_PATH)
    df["Vote Count"] = 0
    df.to_csv(FILE_PATH, index=False)

    return "✅ Đã reset dữ liệu!"

# =========================
# Run app
# =========================
if __name__ == "__main__":
    app.run(debug=True)
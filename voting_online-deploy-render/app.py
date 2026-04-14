from flask import Flask, render_template, request, redirect, session, flash, jsonify, send_from_directory
from eth_account.messages import encode_defunct
from eth_account import Account
from werkzeug.utils import secure_filename
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "123456"
app.config['SESSION_COOKIE_NAME'] = 'voting_session'
app.config['TEMPLATES_AUTO_RELOAD'] = True

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Giới hạn 16MB

# Đường dẫn file CSV
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATH = os.path.join(BASE_DIR, "database/cand_list.csv")
ELECTION_FILE_PATH = os.path.join(BASE_DIR, "database/elections.csv")
IMG_DIR = os.path.join(BASE_DIR, "img")

if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# =========================
# Đọc danh sách ứng viên
# =========================
def get_candidates():
    db_dir = os.path.dirname(FILE_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)

    if not os.path.exists(FILE_PATH):
        # Khởi tạo 10 ứng viên mặc định như yêu cầu
        data = []
        for i in range(1, 11):
            data.append({
                "Name": f"Ứng viên {i}",
                "Image": f"nhanvat{i}.jpg",
                "Description": f"Mô tả chi tiết về ứng viên số {i}",
                "Vote Count": 0
            })
        df = pd.DataFrame(data)
        df.to_csv(FILE_PATH, index=False)

    df = pd.read_csv(FILE_PATH)
    for col in ["Name", "Image", "Description", "Vote Count"]:
        if col not in df.columns:
            df[col] = 0 if col == "Vote Count" else ""
    return df

def get_elections():
    if not os.path.exists(ELECTION_FILE_PATH):
        df = pd.DataFrame(columns=["Code", "Name", "Candidates"])
        # Tạo 1 cuộc bầu cử mẫu
        # Khởi tạo cuộc bầu cử mặc định bao gồm đầy đủ 10 ứng viên
        candidate_names = [f"Ứng viên {i}" for i in range(1, 11)]
        candidates_str = ",".join(candidate_names)
        new_row = pd.DataFrame([{"Code": "VOTE2024", "Name": "Bầu cử Đại biểu 2024", "Candidates": candidates_str}])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(ELECTION_FILE_PATH, index=False)
    return pd.read_csv(ELECTION_FILE_PATH)


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
        
        elections = get_elections()
        election = elections[elections["Code"] == votecode]
        
        if election.empty:
            flash("❌ Mã bầu cử không hợp lệ!", "error")
            return render_template("login.html")
        
        if not username:
            flash("❌ Vui lòng nhập tên đăng nhập!", "error")
            return render_template("login.html")
        
        # Lưu vào session
        session["votecode"] = votecode
        session["user"] = username
        session["election_name"] = election.iloc[0]["Name"]
        return redirect("/vote_page")
    return render_template("login.html")


# =========================
# Trang vote
# =========================
@app.route("/vote_page")
def vote_page():
    if "user" not in session:
        return redirect("/")

    elections = get_elections()
    current_election = elections[elections["Code"] == session.get("votecode")].iloc[0]
    
    # Lọc danh sách ứng viên dựa trên cuộc bầu cử
    allowed_candidates = [c.strip() for c in str(current_election["Candidates"]).split(",")]
    
    all_candidates = get_candidates()
    filtered_candidates = all_candidates[all_candidates["Name"].isin(allowed_candidates)]
    
    return render_template("vote.html", 
                         candidates=filtered_candidates.to_dict(orient="records"),
                         election_name=session.get("election_name"))


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
# QUẢN TRỊ (ADMIN)
# =========================
@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    if not session.get("is_admin"):
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            ADMIN_USER = os.getenv("ADMIN_USER", "admin")
            ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
            if username == ADMIN_USER and password == ADMIN_PASS:
                session["is_admin"] = True
                return redirect("/admin")
            flash("❌ Sai tài khoản hoặc mật khẩu admin!", "error")
        return render_template("admin_login.html")
        
    df = get_candidates()
    elections = get_elections()
    # Lấy danh sách ảnh có sẵn trong thư mục img
    image_files = [f for f in os.listdir(IMG_DIR) if allowed_file(f)]
    return render_template("admin.html", 
                         candidates=df.to_dict(orient="records"), 
                         elections=elections.to_dict(orient="records"),
                         image_files=image_files)

@app.route("/admin/add_candidate", methods=["POST"])
def add_candidate():
    if not session.get("is_admin"): return redirect("/")
    name = request.form.get("name", "").strip()
    image_name = request.form.get("image", "").strip()
    description = request.form.get("description", "").strip()

    if name and image_name:
        df = get_candidates()
        new_row = pd.DataFrame([{
            "Name": name, 
            "Image": image_name, 
            "Description": description, 
            "Vote Count": 0
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(FILE_PATH, index=False)
        flash(f"✅ Đã thêm ứng viên {name}", "success")
    else:
        flash("❌ Vui lòng nhập đầy đủ tên và tên file ảnh!", "error")
    return redirect("/admin")

@app.route("/admin/delete_candidate/<name>")
def delete_candidate(name):
    if not session.get("is_admin"): return redirect("/")
    df = get_candidates()
    df = df[df["Name"] != name]
    df.to_csv(FILE_PATH, index=False)
    flash(f"🗑️ Đã xóa ứng viên {name}", "info")
    return redirect("/admin")

@app.route("/admin/add_election", methods=["POST"])
def add_election():
    if not session.get("is_admin"): return redirect("/")
    code = request.form.get("code", "").strip()
    name = request.form.get("name", "").strip()
    selected_candidates = request.form.getlist("selected_candidates")

    if code and name and selected_candidates:
        df = get_elections()
        if code in df["Code"].values:
            flash("❌ Mã bầu cử này đã tồn tại!", "error")
        else:
            new_row = pd.DataFrame([{"Code": code, "Name": name, "Candidates": ",".join(selected_candidates)}])
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_csv(ELECTION_FILE_PATH, index=False)
            flash(f"✅ Đã tạo cuộc bầu cử: {name}", "success")
    else:
        flash("❌ Vui lòng nhập đầy đủ thông tin và chọn ít nhất 1 ứng viên!", "error")
    return redirect("/admin")

@app.route("/admin/delete_election/<code>")
def delete_election(code):
    if not session.get("is_admin"): return redirect("/")
    df = get_elections()
    df = df[df["Code"] != code]
    df.to_csv(ELECTION_FILE_PATH, index=False)
    flash(f"🗑️ Đã xóa cuộc bầu cử {code}", "info")
    return redirect("/admin")

@app.route("/admin/reset")
def reset_votes():
    if not session.get("is_admin"): return redirect("/")
    df = get_candidates()
    df["Vote Count"] = 0
    df.to_csv(FILE_PATH, index=False)
    flash("🔄 Đã reset toàn bộ kết quả bầu cử!", "warning")
    return redirect("/admin")

@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect("/admin")

@app.after_request
def add_header(response):
    # Ngăn trình duyệt lưu cache để đảm bảo mọi thay đổi giao diện hiện ngay lập tức
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# =========================
# Run app
# =========================
if __name__ == "__main__":
    # Chạy với debug=True để thấy lỗi chi tiết và tự động restart khi lưu file
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
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
        # Khởi tạo ứng viên mặc định
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

    # Đảm bảo các cột cần thiết tồn tại
    for col in ["Name", "Image", "Description", "Vote Count"]:
        if col not in df.columns:
            df[col] = 0 if col == "Vote Count" else ""

    # Loại bỏ các hàng không có tên ứng viên
    df = df[df["Name"].notna() & (df["Name"].str.strip() != "")]

    # Chuẩn hoá cột Image: đảm bảo đường dẫn đúng định dạng
    def fix_image(img):
        if pd.isna(img) or str(img).strip() == "":
            return "nhanvat1.jpg"
        img = str(img).strip()
        # Đã có /img/ prefix thì giữ nguyên
        if img.startswith("/img/"):
            return img
        # Có http thì giữ nguyên
        if img.startswith("http"):
            return img
        return img
    df["Image"] = df["Image"].apply(fix_image)

    return df

def get_elections():
    if not os.path.exists(ELECTION_FILE_PATH):
        df = pd.DataFrame(columns=["Code", "Name", "Candidates", "Allowed Wallets"])
        df.to_csv(ELECTION_FILE_PATH, index=False)
    df = pd.read_csv(ELECTION_FILE_PATH)
    if "Allowed Wallets" not in df.columns:
        df["Allowed Wallets"] = ""
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
        
        elections = get_elections()
        election = elections[elections["Code"] == votecode]
        
        if election.empty:
            flash("❌ Mã bầu cử không hợp lệ!", "error")
            return render_template("login.html")

        # Kiểm tra nếu cuộc bầu cử này yêu cầu ví (whitelist) thì không cho đăng nhập thường
        allowed_str = str(election.iloc[0].get("Allowed Wallets", "")).strip()
        if allowed_str and allowed_str.lower() != "nan" and allowed_str != "":
            flash("❌ Cuộc bầu cử này giới hạn địa chỉ ví. Vui lòng đăng nhập bằng MetaMask!", "error")
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
    votecode = session.get("votecode", "")
    filtered_elections = elections[elections["Code"] == votecode]

    all_candidates = get_candidates()

    if filtered_elections.empty:
        # Không tìm thấy cuộc bầu cử → hiển thị tất cả ứng viên làm fallback
        print(f"[WARN] Không tìm thấy election với code='{votecode}', hiển thị tất cả ứng viên.")
        return render_template("vote.html",
                               candidates=all_candidates.to_dict(orient="records"),
                               election_name=session.get("election_name", "Bầu Cử"))

    current_election = filtered_elections.iloc[0]

    # Lọc danh sách ứng viên dựa trên cuộc bầu cử (strip whitespace)
    allowed_candidates = [c.strip() for c in str(current_election.get("Candidates", "")).split(",") if c.strip()]

    if allowed_candidates:
        filtered_candidates = all_candidates[all_candidates["Name"].isin(allowed_candidates)]
    else:
        filtered_candidates = pd.DataFrame()

    # Fallback: nếu không lọc được ứng viên nào → hiển thị tất cả
    if filtered_candidates.empty:
        print(f"[WARN] Election '{votecode}' có candidates {allowed_candidates} nhưng không khớp CSV. Hiển thị tất cả.")
        filtered_candidates = all_candidates

    return render_template("vote.html",
                           candidates=filtered_candidates.to_dict(orient="records"),
                           election_name=session.get("election_name", current_election["Name"]))


# =========================
# =========================
# Route vote (KHÔNG gọi blockchain nữa)
# =========================
@app.route("/vote", methods=["POST"])
def vote():
    name = request.form.get("candidate", "")
    flash(f"🟡 Đã gửi yêu cầu vote cho {name} (xác nhận trên MetaMask)", "info")
    return redirect("/vote_page")


# =========================
# API: Ghi nhận vote sau khi MetaMask confirm thành công
# =========================
@app.route("/api/record_vote", methods=["POST"])
def record_vote():
    """
    Được gọi từ frontend sau khi giao dịch blockchain được xác nhận.
    Cập nhật Vote Count trong CSV để trang /result hiển thị đúng.
    """
    if "user" not in session:
        return jsonify({"success": False, "error": "Chưa đăng nhập."})

    data = request.get_json()
    data.pop("data", None)
    if not data:
        return jsonify({"success": False, "error": "Dữ liệu không hợp lệ."})

    candidate_name = data.get("candidate", "").strip()
    tx_hash        = data.get("tx_hash", "")
    voter_address  = data.get("address", "")

    # Kiểm tra quyền bầu cử dựa trên whitelist của cuộc bầu cử
    votecode = session.get("votecode")
    if votecode:
        elections = get_elections()
        election = elections[elections["Code"] == votecode]
        if not election.empty:
            allowed_str = str(election.iloc[0].get("Allowed Wallets", "")).strip()
            if allowed_str and allowed_str.lower() != "nan" and allowed_str != "":
                allowed_list = [a.strip().lower() for a in allowed_str.split(",") if a.strip()]
                if voter_address.lower() not in allowed_list:
                    return jsonify({"success": False, "error": "Ví của bạn không có quyền bầu cử trong cuộc này."})

    if not candidate_name:
        return jsonify({"success": False, "error": "Thiếu tên ứng viên."})

    try:
        df = get_candidates()

        # Tìm ứng viên theo tên (so sánh không phân biệt hoa thường)
        mask = df["Name"].str.strip().str.lower() == candidate_name.strip().lower()
        if not mask.any():
            return jsonify({"success": False, "error": f"Không tìm thấy ứng viên '{candidate_name}'."})

        # Tăng Vote Count
        df.loc[mask, "Vote Count"] = df.loc[mask, "Vote Count"].fillna(0).astype(int) + 1
        df.to_csv(FILE_PATH, index=False)

        current_votes = int(df.loc[mask, "Vote Count"].values[0])
        print(f"[VOTE] {voter_address[:8] if voter_address else '?'}... → {candidate_name} | TX: {tx_hash[:10] if tx_hash else '?'}... | Tổng: {current_votes}")

        return jsonify({
            "success": True,
            "candidate": candidate_name,
            "new_vote_count": current_votes,
            "tx_hash": tx_hash
        })

    except Exception as e:
        print(f"[ERROR] record_vote: {e}")
        return jsonify({"success": False, "error": str(e)})


# =========================
# Trang kết quả
# =========================
@app.route("/result")
def result():
    df = get_candidates()
    all_candidates = df.to_dict(orient="records")

    # Lọc theo cuộc bầu cử nếu user đang đăng nhập
    election_name = None
    total_votes = 0

    if "votecode" in session:
        elections = get_elections()
        votecode = session.get("votecode", "")
        filtered_elections = elections[elections["Code"] == votecode]

        if not filtered_elections.empty:
            current_election = filtered_elections.iloc[0]
            election_name = current_election["Name"]
            allowed = [c.strip() for c in str(current_election.get("Candidates", "")).split(",") if c.strip()]
            if allowed:
                filtered_df = df[df["Name"].isin(allowed)]
                if not filtered_df.empty:
                    all_candidates = filtered_df.to_dict(orient="records")

    total_votes = sum(c.get("Vote Count", 0) or 0 for c in all_candidates)

    return render_template("result.html",
                           candidates=all_candidates,
                           election_name=election_name,
                           total_votes=total_votes)


# =========================
# API: Live results (polling)
# =========================
@app.route('/api/live_results')
def live_results():
    """Trả về kết quả vote hiện tại dạng JSON để frontend tự refresh không cần reload trang."""
    try:
        df = get_candidates()
        all_candidates = df.to_dict(orient="records")

        # Lọc theo cuộc bầu cử nếu đang đăng nhập
        if "votecode" in session:
            elections = get_elections()
            votecode = session.get("votecode", "")
            fe = elections[elections["Code"] == votecode]
            if not fe.empty:
                allowed = [c.strip() for c in str(fe.iloc[0].get("Candidates", "")).split(",") if c.strip()]
                if allowed:
                    filtered = df[df["Name"].isin(allowed)]
                    if not filtered.empty:
                        all_candidates = filtered.to_dict(orient="records")

        total = sum(int(c.get("Vote Count", 0) or 0) for c in all_candidates)

        # Làm sạch dữ liệu trước khi trả về JSON
        clean = []
        for c in all_candidates:
            clean.append({
                "Name": str(c.get("Name", "")),
                "Vote Count": int(c.get("Vote Count", 0) or 0),
                "Image": str(c.get("Image", "")),
                "Description": str(c.get("Description", "") or "")
            })

        return jsonify({"success": True, "candidates": clean, "total_votes": total})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# =========================
# Đăng nhập bằng MetaMask
# =========================
@app.route('/login_wallet', methods=['POST'])
def login_wallet():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Dữ liệu không hợp lệ."})

    address = data.get("address", "").strip()
    signature = data.get("signature", "")
    message = data.get("message", "")
    votecode = str(data.get("votecode", "")).strip()

    if not address or not signature or not message:
        return jsonify({"success": False, "error": "Thiếu thông tin xác thực."})

    elections = get_elections()

    if votecode:
        # Người dùng chỉ định code cụ thể
        election = elections[elections["Code"] == votecode]
        if election.empty:
            return jsonify({"success": False, "error": f"Mã bầu cử '{votecode}' không tồn tại."})
    else:
        # Không nhập votecode → dùng cuộc bầu cử đầu tiên có sẵn
        if elections.empty:
            # Không có cuộc bầu cử → vẫn đăng nhập được, hiển thị tất cả ứng viên
            election = pd.DataFrame([{"Code": "", "Name": "Bầu Cử", "Candidates": ""}])
            votecode = ""
        else:
            election = elections.iloc[[0]]
            votecode = election.iloc[0]["Code"]

    try:
        # Xác minh chữ ký MetaMask
        msg = encode_defunct(text=message)
        recovered_address = Account.recover_message(msg, signature=signature)

        if recovered_address.lower() == address.lower():
            # KIỂM TRA WHITELIST (Địa chỉ ví được phép)
            current_election = election.iloc[0]
            allowed_str = str(current_election.get("Allowed Wallets", "")).strip()
            
            if allowed_str and allowed_str.lower() != "nan" and allowed_str != "":
                allowed_list = [a.strip().lower() for a in allowed_str.split(",") if a.strip()]
                if address.lower() not in allowed_list:
                    return jsonify({"success": False, "error": "Địa chỉ ví này không được cấp phép tham gia cuộc bầu cử này."})

            session["user"] = address
            session["votecode"] = votecode
            session["election_name"] = election.iloc[0]["Name"]
            print(f"[OK] MetaMask login: {address[:8]}... → Election: {votecode}")
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Chữ ký MetaMask không hợp lệ."})

    except Exception as e:
        print("[ERROR] login_wallet:", e)
        return jsonify({"success": False, "error": "Lỗi xác minh chữ ký: " + str(e)})


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
    allowed_wallets = request.form.get("allowed_wallets", "").strip()

    if code and name and selected_candidates:
        df = get_elections()
        if code in df["Code"].values:
            flash("❌ Mã bầu cử này đã tồn tại!", "error")
        else:
            new_row = pd.DataFrame([{
                "Code": code, 
                "Name": name, 
                "Candidates": ",".join(selected_candidates),
                "Allowed Wallets": allowed_wallets
            }])
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
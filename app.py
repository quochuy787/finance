import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
# nếu sử dụng app.jinja_env.filters["usd"] = usd cần định nghĩa index.html theo cú pháp {{ value | filter_name }}
app.jinja_env.globals["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")
# Tạo bảng users
db.execute("""CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    hash TEXT NOT NULL,
    cash REAL DEFAULT 10000
);""")
# Tạo bảng portfolio
db.execute("""
    CREATE TABLE IF NOT EXISTS portfolio (
        user_id INTEGER,
        symbol TEXT,
        name TEXT,
        shares INTEGER,
        price FLOAT,
        PRIMARY KEY (user_id, symbol),
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
""")

# Tạo bảng transactions
db.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        symbol TEXT,
        shares INTEGER,
        price FLOAT,
        transaction_type TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
);
""")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.route("/")
@login_required
def index():
    # truy vấn dữ liệu danh sách đầu tư
    rows = db.execute("""SELECT symbol,name,SUM(shares) AS shares,price FROM portfolio WHERE user_id = ?
                      GROUP BY symbol,name,price
                      HAVING shares > 0""", session["user_id"])
    # tinh toan
    cash = db.execute("SELECT cash FROM users WHERE id= ?", session["user_id"])[0]["cash"]
    total_value = round(cash + sum(row["shares"] * row["price"] for row in rows), 2)

    return render_template("index.html", stocks=rows, cash=cash, total_value=total_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares", type=int)

        if not symbol or not shares or shares <= 0:
            return apology("Invalid symbol or number of shares", 400)

        stock = lookup(symbol)
        if not stock:
            return apology("Invalid stock symbol", 400)
        print(stock)

        price = stock["price"]
        total_cost = round(shares * price, 2)
        if round(price, 2) == 28.00:
            print(f"Buying stock at price 28.00: {symbol}")

        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        if total_cost > user_cash:
            return apology("Not enough cash", 400)

        # Kiểm tra cổ phiếu đã có trong danh mục hay chưa
        existing_stock = db.execute(
            "SELECT shares FROM portfolio WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
        if existing_stock:
            db.execute("UPDATE portfolio SET shares = shares + ? WHERE user_id = ? AND symbol = ?",
                       shares, session["user_id"], symbol)
        else:
            db.execute("INSERT INTO portfolio (user_id, symbol, name, shares, price) VALUES (?, ?, ?, ?, ?)",
                       session["user_id"], symbol, stock["name"], shares, price)

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transaction_type) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], symbol, shares, price, "BUY")

        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", total_cost, session["user_id"])

        return redirect("/")
    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    print(f"User ID: {session['user_id']}")  # Kiểm tra giá trị session["user_id"]
    rows = db.execute("""SELECT symbol, shares, price, transaction_type, timestamp
                         FROM transactions
                         WHERE user_id = ?
                         ORDER BY timestamp DESC""", session["user_id"])

    for row in rows:
        print(
            f"Transaction - Symbol: {row['symbol']}, Shares: {row['shares']}, Price: {row['price']}")
    return render_template("history.html", transactions=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    # Forget any user_id
    session.clear()

    if request.method == "POST":
        # Lấy username từ form
        username = request.form.get("username")

        # Truy vấn cơ sở dữ liệu để lấy thông tin người dùng
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        # Kiểm tra username và password
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("Invalid username or password", 403)

        # Lưu user_id vào session
        session["user_id"] = rows[0]["id"]

        # Lưu giá trị cash vào session
        session["cash"] = rows[0]["cash"]

        return redirect("/")

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "POST":
        # nhap ki hieu
        symbol = request.form.get("symbol")
        # kiem tra nếu không có symbol
        if not symbol:
            return apology("must provide symbol", 400)
        # tạo cổ phiếu
        stock = lookup(symbol)
        # nếu không có
        if not stock:
            return apology("invalid symbol stock", 400)
        # hiển thị trang thông tin cổ phiếu
        return render_template("/quoted.html", stock=stock)
    else:
        # hiển thị form thông tin để điền cổ phiếu
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Kiểm tra username, password, confirmation
        if not username:
            return apology("must provide username", 400)
        elif not password or not confirmation:
            return apology("must provide password", 400)
        elif password != confirmation:
            return apology("Password not match", 400)

        # Kiểm tra xem username đã tồn tại chưa
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        if len(rows) > 0:
            # tránh sử dụng flash để xảy ra lỗi
            # Return 400 here, instead of using flash
            return apology("Username already exists", 400)

        # Mã hóa mật khẩu
        hash = generate_password_hash(password, method="scrypt")

        # Thêm người dùng vào cơ sở dữ liệu
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hash)

        # Lấy id của người dùng vừa đăng ký và lưu vào session
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares", type=int)

        if not symbol:
            return apology("must provide symbol", 400)

        if not shares or shares <= 0:
            return apology("Invalid shares", 400)

        # Kiểm tra cổ phiếu trong danh mục đầu tư
        stock = db.execute(
            "SELECT shares FROM portfolio WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
        if not stock or stock[0]["shares"] < shares:
            return apology("Not enough shares", 400)

        # Tìm giá trị cổ phiếu
        stock_data = lookup(symbol)
        if not stock_data:
            return apology("Invalid stock symbol", 400)

        price = stock_data["price"]
        total_sale = shares * price
        if round(price, 2) == 28.00:
            print(f"Selling stock at price 28.00: {symbol}")

        # Cập nhật cổ phiếu
        db.execute("UPDATE portfolio SET shares = shares - ? WHERE user_id = ? AND symbol = ?",
                   shares, session["user_id"], symbol)

        # Xóa cổ phiếu nếu không còn shares
        db.execute("DELETE FROM portfolio WHERE user_id = ? AND symbol = ? AND shares <= 0",
                   session["user_id"], symbol)

        # Cộng tiền vào tài khoản người dùng
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total_sale, session["user_id"])

        # Lưu giao dịch
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, transaction_type) VALUES (?, ?, ?, ?, ?)",
                   session["user_id"], symbol, -shares, price, "SELL")

        return redirect("/")
    else:
        # Lấy danh sách cổ phiếu mà người dùng đang sở hữu
        stocks = db.execute(
            "SELECT symbol FROM portfolio WHERE user_id = ? AND shares > 0", session["user_id"])
        return render_template("sell.html", stocks=stocks)

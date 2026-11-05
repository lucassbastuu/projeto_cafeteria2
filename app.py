import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from database import close_db, get_db, init_db

COFFEES = [
    {
        "name": "Café Expresso",
        "description": "Dose curta, intensa e aromática.",
        "price": 6.00,
    },
    {
        "name": "Cappuccino",
        "description": "Espresso com leite vaporizado e espuma cremosa.",
        "price": 10.00,
    },
    {
        "name": "Café com Leite",
        "description": "Café coado suave com leite quente.",
        "price": 8.00,
    },
    {
        "name": "Mocha",
        "description": "Espresso, chocolate e leite.",
        "price": 12.00,
    },
    {
        "name": "Café Gelado",
        "description": "Café gelado, leve e refrescante.",
        "price": 11.00,
    },
]

PAYMENT_METHODS = ("PIX", "Dinheiro", "Cartão de crédito", "Cartão de débito")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Hash fixo só para igualar o tempo de verificação quando o e-mail não existe.
DUMMY_HASH = generate_password_hash("timing-only")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

_env = os.environ.get("FLASK_ENV", "development")
_secret = os.environ.get("SECRET_KEY")
if _secret:
    app.secret_key = _secret
elif _env == "development":
    app.secret_key = "dev-cafeteria-local-only"
else:
    raise RuntimeError("Defina a variável de ambiente SECRET_KEY.")

app.teardown_appcontext(close_db)
init_db()


def brl(value):
    return "R$ " + f"{value:.2f}".replace(".", ",")


def menu_items():
    return [{**coffee, "price_label": brl(coffee["price"])} for coffee in COFFEES]


def coffee_by_name(name):
    for coffee in COFFEES:
        if coffee["name"] == name:
            return coffee
    return None


def normalize_spaces(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def current_user():
    if "current_user" in g:
        return g.current_user
    user = None
    user_id = session.get("user_id")
    if user_id is not None:
        user = get_db().execute(
            "SELECT id, name, email FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            session.clear()
    g.current_user = user
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            flash("Faça login para continuar.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def ensure_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def csrf_valid():
    sent = request.form.get("csrf_token", "")
    saved = session.get("csrf_token", "")
    if not sent or not saved or len(sent) != len(saved):
        return False
    return secrets.compare_digest(sent, saved)


@app.before_request
def protect_post():
    ensure_csrf_token()
    if request.method == "POST" and not csrf_valid():
        flash("Não foi possível validar o formulário. Tente novamente.", "error")
        return redirect(request.path or url_for("login"))


@app.context_processor
def inject_globals():
    user = current_user()
    return {
        "csrf_token": ensure_csrf_token(),
        "current_user": user,
        "first_name": user["name"].split()[0] if user else "",
    }


def flash_errors(errors):
    for message in errors:
        flash(message, "error")


def validate_registration(form):
    errors = []
    name = normalize_spaces(form.get("name", ""))
    email = normalize_spaces(form.get("email", "")).lower()
    password = form.get("password", "")
    confirm = form.get("password_confirm", "")

    if len(name.split()) < 2 or not 2 <= len(name) <= 80:
        errors.append("Informe nome e sobrenome (até 80 caracteres).")
    if not EMAIL_RE.fullmatch(email) or len(email) > 254:
        errors.append("Informe um e-mail válido.")
    if not isinstance(password, str) or len(password) < 8 or len(password) > 128:
        errors.append("A senha deve ter entre 8 e 128 caracteres.")
    elif password != confirm:
        errors.append("As senhas não conferem.")

    if errors:
        return None, errors
    return {"name": name, "email": email, "password": password}, []


def validate_order(form):
    errors = []
    coffee_name = form.get("coffee", "")
    cup_name = normalize_spaces(form.get("cup_name", ""))
    payment = form.get("payment", "")

    if coffee_by_name(coffee_name) is None:
        errors.append("Escolha um café do cardápio.")
    if not 2 <= len(cup_name) <= 30:
        errors.append("O nome no copo deve ter entre 2 e 30 caracteres.")
    if payment not in PAYMENT_METHODS:
        errors.append("Escolha uma forma de pagamento válida.")

    if errors:
        return None, errors
    return {"coffee": coffee_name, "cup_name": cup_name, "payment": payment}, []


def order_summary(data):
    coffee = coffee_by_name(data["coffee"])
    return {
        "coffee": coffee["name"],
        "price": brl(coffee["price"]),
        "cup_name": data["cup_name"],
        "payment": data["payment"],
    }


def render_order_form(selected="", cup_name="", payment=""):
    return render_template(
        "pedido.html",
        coffees=menu_items(),
        payments=PAYMENT_METHODS,
        selected=selected,
        cup_name=cup_name,
        payment=payment,
        summary=None,
    )


@app.get("/")
@login_required
def index():
    return render_template("index.html", coffees=menu_items())


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user() is not None:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = normalize_spaces(request.form.get("email", "")).lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT id, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        hashed = user["password_hash"] if user else DUMMY_HASH
        password_ok = check_password_hash(hashed, password)
        if user and password_ok:
            session.clear()
            session["user_id"] = user["id"]
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("index"))
        flash("E-mail ou senha inválidos.", "error")

    return render_template("login.html")


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if current_user() is not None:
        return redirect(url_for("index"))

    form = {"name": "", "email": ""}
    if request.method == "POST":
        data, errors = validate_registration(request.form)
        form["name"] = normalize_spaces(request.form.get("name", ""))
        form["email"] = normalize_spaces(request.form.get("email", ""))
        if errors:
            flash_errors(errors)
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                get_db().execute(
                    """
                    INSERT INTO users (name, email, password_hash, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        data["name"],
                        data["email"],
                        generate_password_hash(data["password"]),
                        now,
                    ),
                )
                get_db().commit()
            except sqlite3.IntegrityError:
                get_db().rollback()
                flash("Este e-mail já está cadastrado.", "error")
            else:
                flash("Cadastro realizado. Faça login para continuar.", "success")
                return redirect(url_for("login"))

    return render_template("cadastro.html", form=form)


@app.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Você saiu da conta.", "success")
    return redirect(url_for("login"))


@app.get("/pedido")
@login_required
def pedido():
    draft = session.get("order_draft") or {}
    selected = request.args.get("cafe") or draft.get("coffee", "")
    if selected and coffee_by_name(selected) is None:
        selected = ""
    return render_order_form(
        selected=selected,
        cup_name=draft.get("cup_name", ""),
        payment=draft.get("payment", ""),
    )


@app.post("/pedido")
@login_required
def pedido_revisar():
    data, errors = validate_order(request.form)
    if errors:
        flash_errors(errors)
        return render_order_form(
            selected=request.form.get("coffee", ""),
            cup_name=request.form.get("cup_name", ""),
            payment=request.form.get("payment", ""),
        )
    session["order_draft"] = data
    return redirect(url_for("resumo"))


@app.get("/pedido/resumo")
@login_required
def resumo():
    draft = session.get("order_draft")
    data, errors = validate_order(draft or {})
    if errors:
        session.pop("order_draft", None)
        return redirect(url_for("pedido"))
    return render_template("pedido.html", summary=order_summary(data), coffees=[])


@app.post("/pedido/resumo")
@login_required
def confirmar_pedido():
    draft = session.get("order_draft")
    data, errors = validate_order(draft or {})
    if errors:
        session.pop("order_draft", None)
        flash_errors(errors)
        return redirect(url_for("pedido"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    get_db().execute(
        """
        INSERT INTO orders (
            user_id, coffee_flavor, cup_name, payment_method, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            current_user()["id"],
            data["coffee"],
            data["cup_name"],
            data["payment"],
            "Em preparo",
            now,
        ),
    )
    get_db().commit()
    session.pop("order_draft", None)
    flash("Pedido confirmado. Seu café está em preparo.", "success")
    return redirect(url_for("historico"))


@app.get("/historico")
@login_required
def historico():
    rows = get_db().execute(
        """
        SELECT cup_name, coffee_flavor, payment_method, status, created_at
        FROM orders
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (current_user()["id"],),
    ).fetchall()
    orders = []
    for row in rows:
        created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        orders.append(
            {
                "cup_name": row["cup_name"],
                "coffee": row["coffee_flavor"],
                "payment": row["payment_method"],
                "status": row["status"],
                "created_at": created.strftime("%d/%m/%Y %H:%M"),
            }
        )
    return render_template("historico.html", orders=orders)


@app.errorhandler(404)
def not_found(_error):
    return "Página não encontrada.", 404


@app.errorhandler(500)
def internal_error(_error):
    return "Ocorreu um erro interno. Tente novamente.", 500


if __name__ == "__main__":
    app.run(debug=_env == "development")

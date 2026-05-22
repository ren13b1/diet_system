from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session, redirect
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from openai import OpenAI, base_url
import os
from google import genai
app = Flask(__name__)
app.secret_key = '123456'

# ================= 数据库连接函数 =================
# def get_db():
#     return pymysql.connect(
#         host='localhost',
#         user='root',
#         password='root',
#         database='diet_plandb',
#         autocommit=True,
#         cursorclass=pymysql.cursors.Cursor
#     )
from urllib.parse import urlparse

def get_db():
    url = urlparse(os.getenv("MYSQL_URL"))

    return pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        port=url.port,
        autocommit=True,
        cursorclass=pymysql.cursors.Cursor
    )

# ================= 首页 =================
@app.route('/')
def index():

    if not session.get('user_id'):
        return redirect('/login_page')

    return render_template('index.html')


# ================= 食物页面 =================
@app.route('/foods_page')
def foods_page():

    if not session.get('user_id'):
        return redirect('/login_page')

    return render_template('foods.html')

# ================= 饮食记录页面 =================
@app.route('/logs_page')
def logs_page():

    if not session.get('user_id'):
        return redirect('/login_page')

    return render_template('logs.html')



# ================= 登录页 =================
@app.route('/login_page')
def login_page():
    return render_template('login.html')

# ================= 注册页 =================
@app.route('/register_page')
def register_page():
    return render_template('register.html')

# ================= 注册 =================
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data['username']
    password = generate_password_hash(data['password'])

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
    if cursor.fetchone():
        cursor.close()
        db.close()
        return {"msg": "用户名已存在"}

    cursor.execute(
        "INSERT INTO users(username, password) VALUES (%s, %s)",
        (username, password)
    )

    cursor.close()
    db.close()
    return {"msg": "注册成功"}

# ================= 登录 =================
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT id, password FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()

    cursor.close()
    db.close()

    if user and check_password_hash(user[1], password):
        session['user_id'] = user[0]
        return {"msg": "登录成功"}
    else:
        return {"msg": "用户名或密码错误"}

# ================= 当前用户 =================
@app.route('/me')
def me():

    user_id = session.get('user_id')
    if not user_id:
        return {"logged_in": False}

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT username, daily_calorie_target, today_calorie
        FROM users
        WHERE id=%s
    """, (user_id,))

    u = cursor.fetchone()

    cursor.close()
    db.close()

    return {
        "logged_in": True,
        "username": u[0],
        "target": u[1] or 2000,
        "today": u[2] or 0
    }

# ================= 退出 =================
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login_page')


# ================= 个人信息页面 =================
@app.route('/profile_page')
def profile_page():

    if not session.get('user_id'):
        return redirect('/login_page')

    return render_template('profile.html')

# ================= 获取个人信息 =================
@app.route('/profile')
def profile():

    user_id = session.get('user_id')

    if not user_id:
        return {"msg":"未登录"},401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            age,
            gender,
            height,
            weight,
            weekly_exercise,
            goal
        FROM users
        WHERE id=%s
    """,(user_id,))

    user = cursor.fetchone()

    cursor.close()
    db.close()

    return {
        "age":user[0],
        "gender":user[1],
        "height":user[2],
        "weight":user[3],
        "weekly_exercise":user[4],
        "goal":user[5]
    }

# ================= 保存个人信息 =================
@app.route('/save_profile', methods=['POST'])
def save_profile():

    user_id = session.get('user_id')

    if not user_id:
        return {"msg":"未登录"}, 401

    data = request.get_json()

    age = data.get('age')
    gender = data.get('gender')
    height = data.get('height')
    weight = data.get('weight')
    weekly_exercise = data.get('weekly_exercise')
    goal = data.get('goal')
    target = data.get('target')

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""

        UPDATE users

        SET
            age=%s,
            gender=%s,
            height=%s,
            weight=%s,
            weekly_exercise=%s,
            goal=%s,
            target=%s

        WHERE id=%s

    """,(

        age,
        gender,
        height,
        weight,
        weekly_exercise,
        goal,
        target,
        user_id
    ))

    db.commit()

    return {
        "msg":"保存成功"
    }
# ================= 食物列表 =================
@app.route('/foods')
def foods():

    db = get_db()

    cursor = db.cursor()

    cursor.execute("""

        SELECT
            id,
            name,
            calories,
            image_path

        FROM foods

    """)

    rows = cursor.fetchall()

    cursor.close()
    db.close()

    result = []

    for r in rows:

        result.append({

            "id": r[0],
            "name": r[1],
            "calories": r[2],
            "image_path": r[3]

        })

    return jsonify(result)

# ================= 添加饮食记录 =================
import os
from werkzeug.utils import secure_filename

@app.route('/add_food', methods=['POST'])
def add_food():

    name = request.form.get('name')
    calories = request.form.get('calories')

    image = request.files.get('image')

    image_path = None

    # 上传图片
    if image and image.filename != "":

        filename = secure_filename(image.filename)

        upload_folder = 'static/uploads'

        # 自动创建目录
        os.makedirs(upload_folder, exist_ok=True)

        save_path = os.path.join(upload_folder, filename)

        image.save(save_path)

        image_path = '/' + save_path

    db = get_db()

    cursor = db.cursor()

    cursor.execute("""

        INSERT INTO foods
        (
            name,
            calories,
            image_path
        )

        VALUES
        (
            %s,
            %s,
            %s
        )

    """, (

        name,
        calories,
        image_path

    ))

    db.commit()

    cursor.close()
    db.close()

    return {"msg":"添加成功"}
@app.route('/add_log', methods=['POST'])
def add_log():

    # ================= 1. 登录校验 =================
    user_id = session.get('user_id')
    if not user_id:
        return {"msg": "请先登录"}, 401

    # ================= 2. 获取前端数据 =================
    data = request.get_json()
    food_name = data.get('food_name')
    calories = float(data.get('calories'))

    # ================= 3. 自动计算 meal_type =================
    hour = datetime.now().hour

    if hour < 10:
        meal_type = "早餐"
    elif hour < 15:
        meal_type = "午餐"
    else:
        meal_type = "晚餐"

    # ================= 4. 数据库连接 =================
    db = get_db()
    cursor = db.cursor()

    # ================= 5. 插入日志（带 meal_type） =================
    cursor.execute("""
        INSERT INTO food_logs(user_id, food_name, calories, log_date, meal_type)
        VALUES (%s, %s, %s, NOW(), %s)
    """, (user_id, food_name, calories, meal_type))

    # ================= 6. 更新用户今日热量 =================
    today = date.today()

    cursor.execute("""
        SELECT today_calorie, last_update
        FROM users
        WHERE id=%s
    """, (user_id,))

    user = cursor.fetchone()

    # 防止 None 报错
    today_calorie = user[0] if user else 0
    last_update = user[1] if user else None

    # ================= 7. 跨天重置逻辑 =================
    if last_update != today:

        cursor.execute("""
            UPDATE users
            SET today_calorie=%s,
                last_update=%s
            WHERE id=%s
        """, (calories, today, user_id))

    else:

        cursor.execute("""
            UPDATE users
            SET today_calorie = today_calorie + %s
            WHERE id=%s
        """, (calories, user_id))

    # ================= 8. 提交 =================
    db.commit()
    cursor.close()
    db.close()

    return {"msg": "记录成功", "meal_type": meal_type}
# ================= 修改记录 =================
@app.route('/update_log', methods=['POST'])
def update_log():

    if 'user_id' not in session:
        return jsonify({'message':'未登录'})

    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""

        UPDATE logs
        SET food_name=%s,
            calories=%s
        WHERE id=%s

    """, (

        data['food_name'],
        data['calories'],
        data['id']

    ))

    conn.commit()

    return jsonify({
        'message':'修改成功'
    })


# ================= AI建议 =================



load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("BASE_URL")
)

# =========================
# 2. AI 饮食建议接口
# =========================
@app.route('/ai_advice')
def ai_advice():

    # =========================
    # 1. 登录检查
    # =========================
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"advice": "请先登录"}), 401

    # =========================
    # 2. 数据库查询
    # =========================
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("""
            SELECT food_name, calories
            FROM food_logs
            WHERE user_id = %s
            AND DATE(log_date) = CURDATE()
        """, (user_id,))

        logs = cursor.fetchall()

    except Exception as e:
        return jsonify({"advice": f"数据库查询失败：{str(e)}"}), 500

    # =========================
    # 3. 无记录
    # =========================
    if not logs:
        return jsonify({"advice": "今天还没有饮食记录哦～"})

    # =========================
    # 4. tuple 转文本
    # =========================
    food_text = "\n".join([
        f"{row[0]} - {row[1]} kcal"
        for row in logs
    ])

    # =========================
    # 5. Prompt
    # =========================
    prompt = f"""
你是一个专业营养师，请根据以下用户今日饮食记录进行分析：

饮食记录：
{food_text}

请输出：
1. 总热量是否合理
2. 营养是否均衡（蛋白质/碳水/脂肪）
3. 1-3条具体建议

要求：
- 中文回答
- 简洁清晰
"""

    # =========================
    # 6. AI调用（Qwen正确方式）
    # =========================
    try:
        response = client.chat.completions.create(
            model=os.getenv("MODEL", "qwen-turbo"),
            messages=[
                {"role": "system", "content": "你是专业营养师"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        advice = response.choices[0].message.content

    except Exception as e:
        return jsonify({"advice": f"AI调用失败：{str(e)}"}), 500

    # =========================
    # 7. 返回结果
    # =========================
    return jsonify({"advice": advice})

@app.route('/ai_goal_advise')
def ai_goal_advise():

    user_id = session.get('user_id')

    if not user_id:
        return {"result": "请先登录"}

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT age, gender, height, weight,
               weekly_exercise, goal, daily_calorie_target
        FROM users
        WHERE id=%s
    """, (user_id,))

    user = cursor.fetchone()

    if not user:
        return {"result": "用户不存在"}

    # ===== 计算 BMI =====
    height_m = float(user[2]) / 100
    weight = float(user[3])
    bmi = weight / (height_m ** 2)

    # ===== AI Prompt（重点：结构化输出）=====
    prompt = f"""
你是一名专业营养与运动科学专家。

请根据用户信息，给出【每日热量目标建议】，并按目标分类输出。

【用户信息】
年龄：{user[0]}
性别：{user[1]}
身高：{user[2]} cm
体重：{user[3]} kg
BMI：{bmi:.1f}
每周运动次数：{user[4]}
当前目标：{user[5]}

---

请严格按以下格式输出：

📊 身体分析：
（简短分析）

🔥 每日热量建议：

- 减脂目标：xxxx kcal
- 维持体重：xxxx kcal
- 增肌目标：xxxx kcal

🎯 推荐用户当前目标：
（根据用户情况选择一个，并说明原因）

💡 补充建议：
（2-3条即可，简洁）

要求：
- 不要长篇大论
- 数据要合理（基于BMI + 活动量）
- 适合普通用户阅读
"""

    response = client.chat.completions.create(
        model=os.getenv("MODEL", "qwen-turbo"),
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    result = response.choices[0].message.content

    return {
        "result": result
    }



import base64
import json
from openai import OpenAI

@app.route('/ai_food_scan', methods=['POST'])
def ai_food_scan():

    user_id = session.get('user_id')
    if not user_id:
        return {"msg": "未登录"}, 401

    file = request.files['image']
    img_bytes = file.read()
    img_base64 = base64.b64encode(img_bytes).decode()

    client = OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("BASE_URL")
    )

    prompt = """
你是一个专业饮食分析AI。

请识别图片中的食物，并估算卡路里。

请严格返回JSON：

{
  "food_name": "",
  "calories": 0,
  "advice": ""
}

规则：
- calories 必须是整数
- 如果有多个食物，合并计算总卡路里
- advice 给出一句简单健康建议
"""

    response = client.chat.completions.create(
        model="qwen-vl-plus",
        messages=[
            {
                "role": "system",
                "content": "你是一个只输出JSON的食物识别AI，不允许输出任何解释、Markdown或代码块，只返回合法JSON。"
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_base64}"
                        }
                    }
                ]
            }
        ]
    )

    result_text = response.choices[0].message.content.strip()

    # =========================
    # ✅ 关键修复：防止 JSON 崩溃
    # =========================
    import json
    import re

    # 提取 JSON（防止 ```json 或废话）
    match = re.search(r"\{.*\}", result_text, re.S)

    if not match:
        return {
            "msg": "AI返回格式错误",
            "raw": result_text
        }

    try:
        result = json.loads(match.group())
    except Exception as e:
        return {
            "msg": "JSON解析失败",
            "error": str(e),
            "raw": result_text
        }

    # =========================
    # 正常取值
    # =========================
    food_name = result.get("food_name", "未知食物")
    calories = result.get("calories", 0)
    advice = result.get("advice", "暂无建议")
    # 只存基础数据
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
    INSERT INTO food_logs (user_id, food_name, calories, log_date)
    VALUES (%s, %s, %s, NOW())
    """, (user_id, food_name, calories))

    db.commit()

    return {
        "msg": "识别成功",
        "data": result
    }
@app.route('/delete_log', methods=['POST'])
def delete_log():

    user_id = session.get('user_id')
    log_id = request.json['id']

    db = get_db()
    cursor = db.cursor()

    # 1️⃣ 查热量
    cursor.execute("""
        SELECT calories FROM food_logs WHERE id=%s
    """, (log_id,))
    cal = cursor.fetchone()[0]

    # 2️⃣ 删除记录
    cursor.execute("""
        DELETE FROM food_logs WHERE id=%s
    """, (log_id,))

    # 3️⃣ 回滚用户 today_calorie
    cursor.execute("""
        UPDATE users
        SET today_calorie = today_calorie - %s
        WHERE id=%s
    """, (cal, user_id))

    db.commit()
    cursor.close()
    db.close()

    return {"msg": "删除成功"}
# ================= 今日统计 =================
@app.route('/today_stats')
def today_stats():
    user_id = session.get('user_id')
    if not user_id:
        return {"msg": "未登录"}

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            SUM(f.calories * l.quantity),
            SUM(f.protein * l.quantity),
            SUM(f.carbs * l.quantity)
        FROM food_logs l
        JOIN foods f ON l.food_id = f.id
        WHERE l.user_id=%s AND DATE(l.log_date)=CURDATE()
    """, (user_id,))

    result = cursor.fetchone()

    cursor.close()
    db.close()

    return {
        "calories": result[0] or 0,
        "protein": result[1] or 0,
        "carbs": result[2] or 0
    }
# ================= 获取饮食记录 =================
@app.route('/logs')
def logs():

    user_id = session.get('user_id')

    if not user_id:
        return {"msg":"未登录"},401

    db = get_db()

    cursor = db.cursor()

    cursor.execute("""

        SELECT
            id,
            food_name,
            calories,
            log_date

        FROM food_logs

        WHERE user_id=%s

        ORDER BY log_date DESC

    """,(user_id,))

    rows = cursor.fetchall()

    cursor.close()
    db.close()

    result = []

    for r in rows:

        result.append({

            "id": r[0],

            "food_name": r[1],

            "calories": r[2],

            "log_date": str(r[3])

        })

    return jsonify(result)
# ================= 记录日摄入 =================
@app.route('/today_summary')
def today_summary():

    user_id = session.get('user_id')

    if not user_id:
        return {"msg":"未登录"},401

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""

        SELECT COALESCE(SUM(calories),0),
               COUNT(*)
        FROM food_logs
        WHERE user_id=%s
        AND DATE(log_date)=CURDATE()

    """,(user_id,))

    row = cursor.fetchone()

    cursor.close()
    db.close()

    return jsonify({
        "total_calories": float(row[0]),
        "count": row[1],
        "target": 2000   # 默认目标（你可以改）
    })

# ================= 启动 =================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)



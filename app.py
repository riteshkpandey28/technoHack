from flask import Flask, render_template, request, url_for, redirect, flash, g, session
from flask import Flask, jsonify
from flask.helpers import send_file
from io import BytesIO

# Review Model
import tensorflow as tf
from transformers import DistilBertTokenizerFast
from transformers import TFDistilBertForSequenceClassification
import numpy

# Recommendation Model
import heapq
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Database
import psycopg2

app = Flask(__name__)
app.secret_key = 'ritesh'

database = 'postgresql://postgres:280525@localhost/wheelbuddy'

def review_model(review):
    loaded_model = TFDistilBertForSequenceClassification.from_pretrained("./model")
    tokenizer = DistilBertTokenizerFast.from_pretrained('distilbert-base-uncased')

    predict_input = tokenizer.encode(review,truncation=True,padding=True,return_tensors="tf")

    tf_output = loaded_model.predict(predict_input)[0]
    tf_prediction = tf.nn.softmax(tf_output, axis=1)
    
    labels = ['Negative','Positive']
    label = tf.argmax(tf_prediction, axis=1)
    label = label.numpy()
    return(labels[label[0]])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session.pop('user', None)

        email = request.form['email']
        password = request.form['password']

        conn = psycopg2.connect(database)
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = '" +
                  email+"' AND password = '"+password+"'")
        r = c.fetchall()

        for i in r:
            if (email == i[2] and password == i[3]):
                session['user'] = i[0]
                return redirect(url_for('owner_places'))
        else:
            flash("Invalid Email or Password", 'invalid')

        conn.close()
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == 'POST':
        name = request.form['username']
        email = request.form['email']
        password = request.form['password']
        profile = request.files['profile']

        conn = psycopg2.connect(database)
        c = conn.cursor()

        c.execute("SELECT email FROM users")
        rs = c.fetchall()
        for rs in rs:
            if email in rs:
                flash("Email already associated with an account", 'validemail')
                break
        else:
            c.execute("""
            INSERT INTO users (name, email, password, profile) VALUES (%s, %s, %s, %s)""", (name, email, password, profile.read()))
            conn.commit()
            flash(
                "Registration successfull ! You can now log in to your account ", 'register')
        conn.close

        return redirect(url_for('home'))

    return render_template('index.html')


@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/user', methods=['POST', 'GET'])
def user():
    if request.method == 'POST':
        conn = psycopg2.connect(database)
        c = conn.cursor()

        facilities = ''
        city = request.form['city']
        state = request.form['state']
        place = request.form['place']
        value = request.form.getlist('check')

        c.execute("""SELECT * FROM places WHERE venue = %s AND state = %s AND city = %s""", (place, state, city))
        placesss = c.fetchall()
        scores = list()
        for rs in placesss:
            text = rs[9]
            li = list(text.split(" "))
            res = len(set(value) & set(li)) / float(len(set(value) | set(li))) * 100
            scores.append(res)
        
        recom = heapq.nlargest(2, range(len(scores)), key=scores.__getitem__)
        percent = heapq.nlargest(2, scores)

        recomend = list()
        for i in recom:
            recomend.append(placesss[i][0])
        
        c.execute("SELECT * FROM places WHERE id = '"+str(recomend[0])+"'")
        place1 = c.fetchone()
        c.execute("SELECT * FROM places WHERE id = '"+str(recomend[1])+"'")
        place2 = c.fetchone()

        c.execute("SELECT * FROM reviews WHERE place = '"+str(recomend[0])+"'")
        review1 = c.fetchall()
        c.execute("SELECT * FROM reviews WHERE place = '"+str(recomend[1])+"'")
        review2 = c.fetchall()
    
        context = {
            'percent': percent,
            'place1': place1,
            'review1': review1,
            'place2': place2,
            'review2': review2,
        }
        return render_template('user.html', **context)
        
    return render_template('user.html')



# ------------------------------ OWNER
@app.route('/owner_places')
def owner_places():
    if g.user:
        conn = psycopg2.connect(database)
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE id = '"+str(session['user'])+"'")
        rs = c.fetchone()

        c.execute("SELECT * FROM places WHERE owner = '"+str(session['user'])+"'")
        place = c.fetchall()

        context = {
            'rs': rs,
            'place': place
        }
        return render_template('owner/places.html', **context)
    return redirect(url_for('home'))

@app.route('/owner_register', methods=['POST', 'GET'])
def owner_register():
    if g.user:
        conn = psycopg2.connect(database)
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE id = '"+str(session['user'])+"'")
        rs = c.fetchone()

        context = {
            'rs': rs,
        }

        if request.method == 'POST':

            facilities = ''

            propertyname = request.form['propertyname']
            propertypic = request.files['propertypic']
            shop = request.form['shop']
            city = request.form['city']
            state = request.form['state']
            pincode = request.form['pincode']
            telephone = request.form['telephone']
            venue = request.form['place']
            owner = session['user']

            value = request.form.getlist('check')
            for values in value:
                facilities += values + " "

            c.execute("""
            INSERT into places (propertyname, propertypic, shop, city, state, pincode, telephone, venue, facilities, owner) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (propertyname, propertypic.read(), shop, city, state, pincode, telephone, venue, facilities, owner))

            conn.commit()
            conn.close()

            flash("New Place added successfully ! ", 'newplace')
            return render_template('owner/registration.html', **context)

        return render_template('owner/registration.html', **context)
    return redirect(url_for('home'))

@app.route('/delete_place<int:id>')
def delete_place(id):
    if g.user:
        conn = psycopg2.connect(database)
        c = conn.cursor()

        c.execute("DELETE FROM places WHERE id = '"+str(id)+"'")
        conn.commit()
        conn.close()
        flash("Place data deleted ! ", 'delete')
        return redirect(url_for('owner_places'))
    return redirect(url_for('home'))

@app.route('/update_place<int:id>', methods=['POST', 'GET'])
def update_place(id):
    conn = psycopg2.connect(database)
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE id = '"+str(session['user'])+"'")
    rs = c.fetchone()

    c.execute("SELECT * FROM places WHERE id = '"+str(id)+"'")
    place = c.fetchone()

    context = {
        'rs': rs,
        'place': place
    }

    if request.method == 'POST':

            facilities = ''

            propertyname = request.form['propertyname']
            propertypic = request.files['propertypic']
            shop = request.form['shop']
            city = request.form['city']
            state = request.form['state']
            pincode = request.form['pincode']
            telephone = request.form['telephone']
            venue = request.form['place']
            owner = session['user']

            value = request.form.getlist('check')
            for values in value:
                facilities += values + ", "

            c.execute("""
            UPDATE places SET (propertyname, propertypic, shop, city, state, pincode, telephone, venue, facilities, owner) = (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) WHERE id = %s
            """, (propertyname, propertypic.read(), shop, city, state, pincode, telephone, venue, facilities, owner, id))

            conn.commit()
            conn.close()

            flash("Place data updated added successfully ! ", 'newplace')
            return redirect(url_for('owner_places'))

    return render_template('owner/updateplace.html', **context)


@app.route('/owner_review<int:id>')
def owner_review(id):
    if g.user:
        conn = psycopg2.connect(database)
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE id = '"+str(session['user'])+"'")
        rs = c.fetchone()

        c.execute("SELECT * FROM reviews WHERE place = '"+str(id)+"'")
        reviews = c.fetchall()

        c.execute("SELECT COUNT(sentiment) FROM reviews WHERE sentiment = 'Positive' AND place = '"+str(id)+"'")
        positive = c.fetchone()

        c.execute("SELECT COUNT(sentiment) FROM reviews WHERE sentiment = 'Negative' AND place = '"+str(id)+"'")
        negative = c.fetchone()
        

        context = {
            'rs': rs,
            'reviews': reviews,
            'positive': positive,
            'negative': negative
        }

        return render_template('owner/review.html', **context,)

@app.route('/owner_profile<int:id>')
def profile(id):
    if g.user:
        conn = psycopg2.connect(database)
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE id = '"+str(id)+"'")
        rs = c.fetchone()
        certificate = rs[4]
        conn.close()

        return send_file(BytesIO(certificate), attachment_filename='flask.png', as_attachment=False)

        return redirect(url_for('owner_home'))
        
@app.route('/place_profile<int:id>')
def place_profile(id):
    conn = psycopg2.connect(database)
    c = conn.cursor()

    c.execute("SELECT * FROM places WHERE id = '"+str(id)+"'")
    rs = c.fetchone()
    certificate = rs[2]

    return send_file(BytesIO(certificate), attachment_filename='flask.png', as_attachment=False)

    return redirect(url_for('owner_place'))

@app.route('/user_place_profile<int:id>')
def user_place_profile(id):
    conn = psycopg2.connect(database)
    c = conn.cursor()

    c.execute("SELECT * FROM places WHERE id = '"+str(id)+"'")
    rs = c.fetchone()
    certificate = rs[2]

    return send_file(BytesIO(certificate), attachment_filename='flask.png', as_attachment=False)

    return redirect(url_for('user'))

@app.route('/review<int:id>', methods=['POST', 'GET'])
def review(id):
    if request.method == 'POST':
        conn = psycopg2.connect(database)
        c = conn.cursor()

        email = request.form['email']
        review = request.form['review']
        place = id
        sentiment = review_model(review)

        c.execute("INSERT INTO reviews (email, review, place, sentiment) VALUES (%s, %s, %s, %s)", (email, review, place, sentiment))
        conn.commit()
        return redirect(url_for('user'))


@app.before_request
def before_request():
    g.user = None
    if 'user' in session:
        g.user = session['user']

if __name__ == "__main__":
    app.run(debug=True, host='192.168.0.103')
    # host='192.168.0.103'
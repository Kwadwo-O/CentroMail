import os

from flask import Flask, flash, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = 'centromail-dev-secret'

messages = [
    {
        'id': 1,
        'sender': 'Not AI',
        'email': 'hello@notai.dev',
        'subject': 'This was created by a human',
        'preview': 'Read the latest message in your inbox.',
        'body': 'Hi team, this project was created by a human. Please review the latest update before launch.',
        'time': 'Tomorrow',
        'unread': True,
        'category': 'primary',
        'starred': True,
    },
    {
        'id': 2,
        'sender': 'Mike Adams',
        'email': 'mike@company.com',
        'subject': 'I am informing you that “I QUIT”.',
        'preview': 'Following up on our conversation.',
        'body': 'After careful consideration, I have decided to leave the role. Please arrange the handover.',
        'time': 'Yesterday',
        'unread': True,
        'category': 'primary',
        'starred': False,
    },
    {
        'id': 3,
        'sender': 'Boss',
        'email': 'boss@company.com',
        'subject': 'What did I tell you about using AI!!!',
        'preview': 'Please review this message.',
        'body': 'The work is not acceptable. Please revise the draft and send it again before noon.',
        'time': '9:20 AM',
        'unread': False,
        'category': 'primary',
        'starred': False,
    },
    {
        'id': 4,
        'sender': 'Automated Message',
        'email': 'security@service.com',
        'subject': 'Code for account: 1948',
        'preview': 'Your security notification.',
        'body': 'Your account verification code is 1948. Do not share it with anyone.',
        'time': '2:00 AM',
        'unread': False,
        'category': 'updates',
        'starred': False,
    },
    {
        'id': 5,
        'sender': 'Elon Musk',
        'email': 'elon@x.com',
        'subject': 'This is a good investment idea',
        'preview': 'Let’s discuss this soon.',
        'body': 'This could be a great move if we scale it smartly. Let’s talk later this week.',
        'time': '1:00 PM',
        'unread': False,
        'category': 'social',
        'starred': False,
    },
]


def make_stats():
    return {
        'total': len(messages),
        'unread': sum(1 for message in messages if message['unread']),
        'starred': sum(1 for message in messages if message['starred']),
        'sent': 12,
    }


@app.route('/')
def index():
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''

        if not email or '@' not in email:
            return render_template(
                'login.html',
                email=email,
                form_error='Please enter a valid email address.',
            ), 400

        if not password:
            return render_template(
                'login.html',
                email=email,
                form_error='Please enter your password.',
            ), 400

        session['user_email'] = email
        flash(f'Welcome back, {email}.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/home')
def home():
    return redirect(url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', stats=make_stats(), user_email=session.get('user_email'))


@app.route('/inbox')
def inbox():
    return render_template('mail.html', messages=messages)


@app.route('/mail')
def mail():
    return render_template('mail.html', messages=messages)


@app.route('/message/<int:message_id>')
def message_detail(message_id):
    for message in messages:
        if message['id'] == message_id:
            return render_template('message.html', message=message)
    return 'Message not found', 404


@app.route('/compose', methods=['GET', 'POST'])
def compose():
    if request.method == 'POST':
        recipient = request.form.get('to', 'unknown@example.com')
        subject = request.form.get('subject') or 'No subject'
        body = request.form.get('body') or ''
        flash(f'Message sent to {recipient} successfully.', 'success')
        print(f'Sent email to {recipient} | Subject: {subject} | Body: {body}')
        return redirect(url_for('inbox'))
    return render_template('compose.html')


@app.route('/settings')
def settings():
    return render_template('settings.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/auth/<provider>')
def authenticate(provider):
    if provider not in {'google', 'microsoft'}:
        return 'Unsupported email provider', 404

    client_id_name = 'GOOGLE_CLIENT_ID' if provider == 'google' else 'MICROSOFT_CLIENT_ID'
    if not os.getenv(client_id_name):
        return render_template(
            'login.html',
            setup_message=f'{provider.title()} sign-in is not configured yet. Add {client_id_name} to your environment before connecting.',
        ), 503

    session['user_email'] = f'{provider}@placeholder.local'
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)

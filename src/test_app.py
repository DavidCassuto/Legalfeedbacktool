# C:\ProjectFT\src\test_app.py

from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello from test_app!"

if __name__ == '__main__':
    print("Attempting to run test_app...")
    app.run(debug=True, port=5001) # Gebruik een andere poort om conflicten te voorkomen
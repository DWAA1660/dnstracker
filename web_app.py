import os
from flask import Flask, jsonify, request, render_template

import db_manager

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    timeframe = request.args.get('timeframe', default=24, type=int)
    stats = db_manager.get_stats(timeframe_hours=timeframe)
    return jsonify(stats)

@app.route('/api/queries/recent')
def get_recent_queries():
    limit = request.args.get('limit', default=50, type=int)
    queries = db_manager.get_recent_queries(limit=limit)
    return jsonify(queries)

@app.route('/api/devices')
def get_devices():
    devices = db_manager.get_devices()
    return jsonify(devices)

@app.route('/api/device/<ip>', methods=['POST'])
def update_device(ip):
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'Name is required'}), 400
    
    db_manager.update_device_name(ip, data['name'])
    return jsonify({'success': True, 'message': 'Device updated'})

if __name__ == '__main__':
    db_manager.init_db()
    app.run(host='0.0.0.0', port=4000, debug=True)

#!/bin/bash
SESSION_NAME="gamma_app"

# 确保 Redis 服务正在运行
# sudo service redis-server status || sudo service redis-server start
echo "Starting Redis server..."
sudo service redis-server start

# 激活 Python 虚拟环境的命令
ACTIVATE_VENV="source ./venv/bin/activate"

# 检查 tmux 会话是否已存在，如果存在则先杀死它
tmux has-session -t $SESSION_NAME 2>/dev/null
if [ $? = 0 ]; then
    tmux kill-session -t $SESSION_NAME
fi

# 创建一个新的、分离的 tmux 会话
echo "Starting tmux session: $SESSION_NAME"
tmux new-session -d -s $SESSION_NAME

# 1. 创建第一个窗口，用于运行 Flask App
tmux new-window -t $SESSION_NAME:1 -n 'Flask'
tmux send-keys -t $SESSION_NAME:1 "$ACTIVATE_VENV" C-m
tmux send-keys -t $SESSION_NAME:1 "flask run --host=0.0.0.0" C-m

# 2. 创建第二个窗口，用于运行 Celery Worker
tmux new-window -t $SESSION_NAME:2 -n 'Celery'
tmux send-keys -t $SESSION_NAME:2 "$ACTIVATE_VENV" C-m
tmux send-keys -t $SESSION_NAME:2 "celery -A tasks.celery worker --loglevel=info -P gevent -c 100" C-m

# 3. 创建第三个窗口，留作一个 shell 方便操作
tmux new-window -t $SESSION_NAME:3 -n 'Shell'
tmux send-keys -t $SESSION_NAME:3 "$ACTIVATE_VENV" C-m
tmux send-keys -t $SESSION_NAME:3 "sudo service redis-server start" C-m

echo "Development environment started in tmux session '$SESSION_NAME'."
echo "Attach to it with: tmux attach-session -t $SESSION_NAME"
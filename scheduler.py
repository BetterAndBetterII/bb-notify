import os
import time
import subprocess
from datetime import datetime
import pytz

def run_notify():
    """运行notify.py脚本"""
    try:
        # 使用subprocess运行notify.py
        result = subprocess.run(['python', 'notify.py'], capture_output=True, text=True)
        
        # 打印执行时间和结果
        current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
        if result.returncode == 0:
            print(f'[{current_time}] 执行成功')
            if result.stdout:
                print(result.stdout)
        else:
            print(f'[{current_time}] 执行失败:')
            if result.stderr:
                print(result.stderr)
            
    except Exception as e:
        print(f'运行出错: {str(e)}')

def main():
    # 从环境变量获取间隔时间(分钟)，默认为30分钟
    interval_minutes = int(os.getenv('NOTIFY_INTERVAL', '30'))
    interval_seconds = interval_minutes * 60
    
    print(f'定时任务已启动，执行间隔: {interval_minutes} 分钟')
    
    while True:
        run_notify()
        time.sleep(interval_seconds)

if __name__ == '__main__':
    main() 
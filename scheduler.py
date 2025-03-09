import os
import time
import subprocess
from datetime import datetime, timedelta
import pytz

def run_notify():
    """运行notify.py脚本并记录日志"""
    log_name = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d %H-%M-%S") + ".log"
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_name)
    try:
        # 使用subprocess运行notify.py
        result = subprocess.run(
            ["python", "notify.py"], capture_output=True, text=True
        )
        
        # 获取当前时间
        current_time = datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y-%m-%d %H-%M-%S')
        
        # 准备日志内容
        log_content = f'[{current_time}] '
        if result.returncode == 0:
            log_content += '执行成功\n'
            if result.stdout:
                log_content += result.stdout
        else:
            log_content += '执行失败:\n'
            if result.stderr:
                log_content += result.stderr
        
        # 打印到控制台
        print(log_content)
        
        # 写入日志文件
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(log_content + '\n')
            
    except Exception as e:
        error_msg = f'运行出错: {str(e)}'
        print(error_msg)
        # 记录错误到日志文件
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d %H-%M-%S")}] {error_msg}\n')

def get_next_run_time(interval_minutes):
    """计算下一个执行时间点"""
    now = datetime.now(pytz.timezone('Asia/Shanghai'))
    
    # 计算当前小时已经过去的分钟数
    minutes_past_hour = now.minute
    
    # 计算下一个执行时间点的分钟数
    next_minutes = ((minutes_past_hour // interval_minutes) + 1) * interval_minutes
    
    # 如果下一个执行时间点超过当前小时，调整到下一个小时的开始
    if next_minutes >= 60:
        next_minutes = 0
        now = now + timedelta(hours=1)
    
    # 设置下一个执行时间
    next_run = now.replace(minute=next_minutes, second=0, microsecond=0)
    return next_run

def main():
    # 从环境变量获取间隔时间(分钟)，默认为30分钟
    interval_minutes = int(os.getenv('NOTIFY_INTERVAL', '30'))
    
    # 验证间隔时间是否为60的约数
    if 60 % interval_minutes != 0:
        raise ValueError(f'间隔时间 {interval_minutes} 分钟不是60的约数，请使用以下值：1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60')
    
    print(f'定时任务已启动，执行间隔: {interval_minutes} 分钟')
    
    while True:
        # 计算下一个执行时间
        next_run = get_next_run_time(interval_minutes)
        
        # 计算需要等待的时间
        now = datetime.now(pytz.timezone('Asia/Shanghai'))
        wait_seconds = (next_run - now).total_seconds()
        
        if wait_seconds > 0:
            print(f'下次执行时间: {next_run.strftime("%Y-%m-%d %H:%M:%S")}')
            time.sleep(wait_seconds)
        
        run_notify()

if __name__ == '__main__':
    main() 
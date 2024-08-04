import logging
import watchtower
import boto3

def setup_logging(use_cloudwatch):

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler for local logging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if use_cloudwatch:
        try:
            cloudwatch_handler = watchtower.CloudWatchLogHandler(
                log_group='Vanii-logs',
                stream_name='Vanii-FlaskBackend-logs'
            )
            cloudwatch_handler.setFormatter(formatter)
            root_logger.addHandler(cloudwatch_handler)
        except Exception as e:
            print(f"Failed to set up CloudWatch logging: {e}")
    
    return root_logger

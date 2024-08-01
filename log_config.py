import logging
import os
import watchtower
import boto3

def setup_logging():

    # Set up root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # CloudWatch handler for AWS logging
    cloudwatch_handler = watchtower.CloudWatchLogHandler(
        log_group='Vanii-logs',
        stream_name='Vanii-FlaskBackend-logs',
        boto3_session=boto3.Session()
    )
    cloudwatch_handler.setFormatter(formatter)
    root_logger.addHandler(cloudwatch_handler)

    return root_logger

logger = setup_logging()
"""AWS Lambda entry point for the Alexa -> JARVIS bridge.

Configure the Lambda with:
    Runtime: Python 3.12
    Handler: lambda_function.lambda_handler
    Trigger: "Alexa Skills Kit" (paste your Skill ID)
    Env vars: JARVIS_ENDPOINT, JARVIS_API_KEY, JARVIS_TIMEOUT, ALEXA_SKILL_ID

Amazon validates the Alexa request signature before it reaches this function
when the "Alexa Skills Kit" trigger is used, so no extra verification is needed here.
"""

from handler import handle_alexa_request


def lambda_handler(event, context):
    return handle_alexa_request(event)

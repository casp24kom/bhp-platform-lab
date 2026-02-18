#!/usr/bin/env python3
import os, json, time
import boto3
from botocore.exceptions import ClientError

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")
MODEL_ID = os.environ.get("MODEL_ID")  # inference profile ARN recommended
AWS_PROFILE = os.environ.get("AWS_PROFILE")  # optional

# Optional: assume a role explicitly for testing (useful to validate the agent role permissions)
ASSUME_ROLE_ARN = os.environ.get("AWS_ROLE_ARN")  # e.g. arn:aws:iam::1845...:role/bhp-platformlab-bedrock-agent-role
ASSUME_ROLE_SESSION = os.environ.get("AWS_ROLE_SESSION_NAME", "bedrock-runtime-smoke")

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "6"))
BASE_DELAY_S = float(os.environ.get("BASE_DELAY_S", "2.0"))

if not MODEL_ID:
    raise SystemExit("Set MODEL_ID (e.g. Bedrock inference profile ARN)")

def mk_session():
    if AWS_PROFILE:
        return boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    return boto3.Session(region_name=AWS_REGION)

def assume_role(sess: boto3.Session, role_arn: str):
    sts = sess.client("sts", region_name=AWS_REGION)
    resp = sts.assume_role(RoleArn=role_arn, RoleSessionName=ASSUME_ROLE_SESSION)
    creds = resp["Credentials"]
    return boto3.Session(
        region_name=AWS_REGION,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )

def explain_error(e: ClientError):
    code = e.response.get("Error", {}).get("Code", "Unknown")
    msg = e.response.get("Error", {}).get("Message", str(e))
    req_id = e.response.get("ResponseMetadata", {}).get("RequestId")
    http = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    print(f"ErrorCode: {code}")
    print(f"HTTPStatus: {http}")
    print(f"RequestId: {req_id}")
    print(f"Message: {msg}")

    if code in ("ThrottlingException", "TooManyRequestsException"):
        print("\nLikely cause: account/model quota exceeded (e.g. tokens/day).")
        print("Next: wait for quota reset or request an increase; reduce traffic/retries; use a different model/profile.")
    elif code in ("AccessDeniedException", "UnauthorizedException"):
        print("\nLikely cause: caller identity lacks bedrock:InvokeModel / bedrock:InvokeModelWithResponseStream for this MODEL_ID.")
        print("Next: confirm your current identity (aws sts get-caller-identity) and attach the required IAM permissions.")
    elif code == "ValidationException":
        print("\nLikely cause: request payload invalid for this model ID (or wrong model interface).")
        print("Next: verify MODEL_ID and payload schema matches the model provider requirements.")
    else:
        print("\nUnhandled error type; inspect message and request id for more detail.")

def main():
    base_sess = mk_session()

    # Print caller identity for clarity
    try:
        sts = base_sess.client("sts", region_name=AWS_REGION)
        ident = sts.get_caller_identity()
        print("CallerIdentity:", json.dumps(ident, indent=2))
    except Exception as ex:
        print("Warning: could not get caller identity:", ex)

    sess = base_sess
    if ASSUME_ROLE_ARN:
        print(f"Assuming role: {ASSUME_ROLE_ARN}")
        sess = assume_role(base_sess, ASSUME_ROLE_ARN)

    br = sess.client("bedrock-runtime", region_name=AWS_REGION)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 32,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Say hello in one short sentence."}]}
        ],
    }

    delay = BASE_DELAY_S
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = br.invoke_model(
                modelId=MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body).encode("utf-8"),
            )
            out = resp["body"].read().decode("utf-8")
            print("\n=== SUCCESS ===")
            print(out[:800])
            return 0

        except ClientError as e:
            print(f"\n=== ClientError (attempt {attempt}/{MAX_RETRIES}) ===")
            explain_error(e)

            code = e.response.get("Error", {}).get("Code", "")
            if code in ("ThrottlingException", "TooManyRequestsException"):
                if attempt == MAX_RETRIES:
                    print("\nFAILED: throttled after max retries.")
                    return 2
                print(f"\nRetrying after {delay:.1f}s...")
                time.sleep(delay)
                delay *= 2
                continue

            # For AccessDenied / Validation etc: don’t retry, fail fast.
            print("\nFAILED: non-retryable error.")
            return 1

        except Exception as ex:
            print("\n=== Unexpected error ===")
            print(repr(ex))
            return 99

if __name__ == "__main__":
    raise SystemExit(main())
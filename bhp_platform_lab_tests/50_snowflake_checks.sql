-- BHP_PLATFORM_LAB – Snowflake validation checklist
-- Run in Snowsight (as ACCOUNTADMIN or your app role)

-- 1) Confirm enriched view exists
SHOW VIEWS LIKE 'SOP_CHUNKS_ENRICHED' IN SCHEMA BHP_PLATFORM_LAB.KB;

-- 2) Confirm Cortex Search services exist (and note service name)
SELECT *
FROM BHP_PLATFORM_LAB.INFORMATION_SCHEMA.CORTEX_SEARCH_SERVICES
WHERE SERVICE_SCHEMA = 'KB'
ORDER BY CREATED DESC;

-- 3) Quick list (alternative)
SHOW CORTEX SEARCH SERVICES IN SCHEMA BHP_PLATFORM_LAB.KB;

-- 4) Test a query directly against a service via SEARCH_PREVIEW
-- Replace <SERVICE_NAME> with the service you see above.
SELECT
  SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
    'BHP_PLATFORM_LAB.KB.<SERVICE_NAME>',
    '{
      "query": "lockout tagout procedure before maintenance",
      "columns": ["DOC_ID","DOC_NAME","CHUNK_ID","CHUNK_TEXT","DOC_TOPIC","DOC_RISK_TIER"],
      "limit": 5
    }'
  ) AS preview_json;

-- 5) Flatten results for readability
SELECT
  r.value:"DOC_ID"::string        AS doc_id,
  r.value:"DOC_NAME"::string      AS doc_name,
  r.value:"CHUNK_ID"::int         AS chunk_id,
  r.value:"DOC_TOPIC"::string     AS doc_topic,
  r.value:"DOC_RISK_TIER"::string AS doc_risk_tier,
  r.value:"CHUNK_TEXT"::string    AS chunk_text
FROM TABLE(
  FLATTEN(
    INPUT => PARSE_JSON(
      SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'BHP_PLATFORM_LAB.KB.<SERVICE_NAME>',
        '{
          "query": "lockout tagout procedure before maintenance",
          "columns": ["DOC_ID","DOC_NAME","CHUNK_ID","CHUNK_TEXT","DOC_TOPIC","DOC_RISK_TIER"],
          "limit": 5
        }'
      )
    ):"results"
  )
) r;

-- 6) Privileges sanity (service runs with owner’s rights; be careful who gets USAGE)
--   Granting USAGE on the service enables querying indexed content.
--   See Snowflake docs for details.

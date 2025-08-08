# Databricks Genie API Integration Demo


![](./assets/genie_room0.png)
![](./assets/genie-space.png)
![](./assets/genie-space4.png)

This repository demonstrates how to integrate Databricks' AI/BI Genie Conversation APIs into custom Databricks Apps applications, allowing users to interact with their structured data using natural language.

You can also click the Generate insights button and generate deep analysis and trends of your data.
![](./assets/insights1.png)
![](./assets/insights2.png)



## Overview

This app is a Dash application featuring a chat interface powered by Databricks Genie Conversation APIs, built specifically to run as a Databricks App. This integration showcases how to leverage Databricks' platform capabilities to create interactive data applications with minimal infrastructure overhead.

The Databricks Genie Conversation APIs (in Public Preview) enable you to embed AI/BI Genie capabilities into any application, allowing users to:
- Ask questions about their data in natural language
- Get SQL-powered insights without writing code
- Follow up with contextual questions in a conversation thread

## Key Features

- **Powered by Databricks Apps**: Deploy and run directly from your Databricks workspace with built-in security and scaling
- **Zero Infrastructure Management**: Leverage Databricks Apps to handle hosting, scaling, and security
- **Workspace Integration**: Access your data assets and models directly from your Databricks workspace
- **Natural Language Data Queries**: Ask questions about your data in plain English
- **Stateful Conversations**: Maintain context for follow-up questions

## Example Use Case

This demo shows how to create a simple interface that connects to the Genie API, allowing users to:
1. Start a conversation with a question about their supply chain data
2. View generated SQL and results
3. Ask follow-up questions that maintain context

## Deploying to Databricks apps

1. Clone the repository to workspace directory such as 
/Workspace/Users/wenwen.xie@databricks.com/genie_space
```bash
git clone https://github.com/vivian-xie-db/genie_space.git
```
![](./assets/genie-space1.png)


2. Change the "SPACE_ID" environment value to the ID of your Genie space, for example, 01f02a31663e19b0a18f1a2ed7a435a7 in the app.yaml file in the root directory and add 
a model serving endpoint in App resources for adding a model for insights generation:

```yaml
command:
- "python"
- "app.py"

env:
- name: "SPACE_ID"
  value: "space_id"
- name: "SERVING_ENDPOINT_NAME"
  valueFrom: "serving_endpoint"

```
![](./assets/genie-space7.png)
![](./assets/genie-space8.png)

3. Create an app in the Databricks apps interface and then deploy the path to the code

![](./assets/genie-space2.png)

4. Grant the service principal can_run permission to the genie space.
![](./assets/genie-space9.png)

5. Grant the service principal permission can_use to the SQL warehouse that powers genie

![](./assets/genie-space5.png)


![](./assets/genie-space6.png)

6. Grant the service principal appropriate privileges to the underlying resources such as catalog, schema and tables.

   note: I am using ALL PRIVILEGES for demo purpose but you can do use catalog on catalog, use schema on schema and select on tables

![](./assets/table1.png)

![](./assets/table2.png)

![](./assets/table3.png)

6. Troubleshooting issues:
   
   For trouble shooting, navigate to the genie room monitoring page and check if the query has been sent successfully to the genie room via the API. 

![](./assets/troubleshooting1.png)

   Click open the query and check if there is any error or any permission issues.


![](./assets/troubleshooting2.png)


## Authentication & Token Management

This application uses a hybrid authentication approach to balance functionality and security:

### **Token Usage Strategy**

#### **Service Principal Token (For Conversation & Query Results)**:
- `start_conversation()` - Falls back to service principal if user token fails
- `send_message()` - Uses service principal directly
- `get_message()` - Uses service principal directly
- `get_query_result()` - Uses service principal directly

#### **User Token + DATABRICKS_SQL_HTTP_PATH (For Query Execution)**:
- `execute_query()` - Uses user token with `DATABRICKS_SQL_HTTP_PATH` for direct SQL execution

### **Environment Variables Required**

```yaml
env:
- name: "SPACE_ID"
  value: "your_genie_space_id"
- name: "DATABRICKS_HOST"
  value: "your_databricks_host"
- name: "DATABRICKS_CLIENT_ID"
  value: "your_client_id"
- name: "DATABRICKS_CLIENT_SECRET"
  value: "your_client_secret"
- name: "DATABRICKS_SQL_HTTP_PATH"
  value: "your_sql_warehouse_http_path"
- name: "GENIE_LOG_TABLE"
  value: "your_audit_table_name"
- name: "SERVING_ENDPOINT_NAME"
  valueFrom: "serving_endpoint"
```

### **DATABRICKS_SQL_HTTP_PATH Usage**

The `DATABRICKS_SQL_HTTP_PATH` environment variable is used for:

1. **Direct SQL Execution**: Bypasses Genie API limitations by executing SQL queries directly through Databricks SQL
2. **User Token Authentication**: Query execution requires proper user permissions via user token
3. **Audit Logging**: Logs conversation and query activities for compliance
4. **Performance**: Direct SQL execution is typically faster than API-based execution

### **Security Benefits**

- **User Token Required**: Query execution requires proper user authentication
- **Service Principal Fallback**: Conversation flow continues even if user token has issues
- **Audit Trail**: Maintains user context for compliance and monitoring
- **Permission Enforcement**: Clear error messages when user lacks required permissions

### **Expected Behavior**

1. **Conversations work smoothly** - Using service principal fallback
2. **Query results work** - Using service principal to fetch results
3. **Query execution works** - Using user token via `DATABRICKS_SQL_HTTP_PATH` for direct SQL execution
4. **Clear error handling** - Proper error messages when permissions are insufficient

## Resources

- [Databricks Genie Documentation](https://docs.databricks.com/aws/en/genie)
- [Conversation APIs Documentation](https://docs.databricks.com/api/workspace/genie)
- [Databricks Apps Documentation](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)
- [Databricks SQL Connector Documentation](https://docs.databricks.com/dev-tools/python-sql-connector.html)
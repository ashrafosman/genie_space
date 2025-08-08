import pandas as pd
import time
import requests
import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional, List, Union, Tuple
import logging
import backoff
import uuid
from token_minter import TokenMinter
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Load environment variables
SPACE_ID = os.environ.get("SPACE_ID")
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST")
CLIENT_ID = os.environ.get("DATABRICKS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("DATABRICKS_CLIENT_SECRET")

token_minter = TokenMinter(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    host=DATABRICKS_HOST
)


class GenieClient:
    def __init__(self, host: str, space_id: str, user_token: str = None):
        self.host = host
        self.space_id = space_id
        self.user_token = user_token
        self.update_headers()
        
        self.base_url = f"https://{host}/api/2.0/genie/spaces/{space_id}"
    
    def update_headers(self, use_service_principal: bool = False, add_user_context: bool = False) -> None:
        """Update headers with user token by default, service principal token only when specified"""
        if not use_service_principal and self.user_token:
            logger.info(f"Using user token for query execution (token length: {len(self.user_token)})")
            access_token = self.user_token
        else:
            logger.info("Using service principal token for API call")
            access_token = token_minter.get_token()
            
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        # Add user context headers if requested and user token is available
        if add_user_context and self.user_token:
            try:
                import base64
                import json
                parts = self.user_token.split('.')
                if len(parts) >= 2:
                    payload_part = parts[1]
                    payload_part += '=' * (4 - len(payload_part) % 4)
                    decoded = base64.b64decode(payload_part)
                    token_data = json.loads(decoded)
                    
                    # Look for user identifier in JWT
                    user_id = token_data.get('sub') or token_data.get('email') or token_data.get('preferred_username')
                    if user_id:
                        self.headers["X-Databricks-User-Context"] = user_id
                        self.headers["X-User-Context"] = user_id
                        logger.info(f"Adding user context headers: {user_id}")
            except Exception as e:
                logger.warning(f"Could not extract user context for headers: {e}")
    
    @backoff.on_exception(
        backoff.expo,
        Exception,  
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def start_conversation(self, question: str) -> Dict[str, Any]:
        """Start a new conversation with the given question"""
        url = f"{self.base_url}/start-conversation"
        payload = {"content": question}
        
        # Try with user token first if available
        if self.user_token:
            logger.info(f"Using user credentials for start-conversation. URL: {url}")
            logger.info(f"User token length: {len(self.user_token)}")
            self.update_headers(use_service_principal=False)
            logger.info(f"Request headers: {self.headers}")
            logger.info(f"Request payload: {payload}")
            
            response = requests.post(url, headers=self.headers, json=payload)
            logger.info(f"User token response status: {response.status_code}")
            
            # If user token fails, fall back to service principal
            if response.status_code in [401, 403]:
                logger.warning(f"User token failed with {response.status_code} for start-conversation, falling back to service principal")
                logger.warning(f"Error response: {response.text}")
                logger.warning(f"Error headers: {dict(response.headers)}")
                self.update_headers(use_service_principal=True)
                response = requests.post(url, headers=self.headers, json=payload)
                logger.info(f"Service principal fallback status: {response.status_code}")
            else:
                logger.info("User credentials worked for start-conversation!")
        else:
            logger.info("No user token available, using service principal for start-conversation")
            self.update_headers(use_service_principal=True)
            response = requests.post(url, headers=self.headers, json=payload)
        
        response.raise_for_status()
        return response.json()
    
    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def send_message(self, conversation_id: str, message: str) -> Dict[str, Any]:
        """Send a follow-up message to an existing conversation"""
        self.update_headers(use_service_principal=True)  # Use service principal for conversation management
        url = f"{self.base_url}/conversations/{conversation_id}/messages"
        payload = {"content": message}
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def get_message(self, conversation_id: str, message_id: str) -> Dict[str, Any]:
        """Get the details of a specific message"""
        self.update_headers(use_service_principal=True)  # Use service principal for message management
        url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}"
        
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def get_query_result(self, conversation_id: str, message_id: str, attachment_id: str) -> Dict[str, Any]:
        """Get the query result using the attachment_id endpoint with service principal
        
        Args:
            conversation_id: The ID of the conversation
            message_id: The ID of the message
            attachment_id: The ID of the attachment containing the query result
            
        Returns:
            Dict containing the query result
            
        Raises:
            Exception: For any request errors
        """
        query_result_url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result"
        
        logger.info(f"Attempting to get query result from: {query_result_url}")
        
        logger.info("Using service principal for query-result")
        self.update_headers(use_service_principal=True)
        
        try:
            response = requests.get(query_result_url, headers=self.headers)
            response.raise_for_status()  # This will raise for any 4XX/5XX errors
            
            result = response.json()
            
            # Extract data_array from the correct nested location
            data_array = []
            if 'statement_response' in result:
                if 'result' in result['statement_response']:
                    data_array = result['statement_response']['result'].get('data_array', [])
                
            return {
                'data_array': data_array,
                'schema': result.get('statement_response', {}).get('manifest', {}).get('schema', {})
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching query result: {str(e)}")
            raise Exception(f"Failed to fetch query result: {str(e)}")

    @backoff.on_exception(
        backoff.expo,
        Exception,  # Retry on any exception
        max_tries=5,
        factor=2,
        jitter=backoff.full_jitter,
        on_backoff=lambda details: logger.warning(
            f"API request failed. Retrying in {details['wait']:.2f} seconds (attempt {details['tries']})"
        )
    )
    def execute_query(self, conversation_id: str, message_id: str, attachment_id: str, query_text: str = None) -> Dict[str, Any]:
        """Execute a query using Databricks SQL with user token only
        
        Args:
            conversation_id: The ID of the conversation
            message_id: The ID of the message
            attachment_id: The ID of the attachment containing the query
            query_text: The SQL query to execute (if not provided, will try to extract from attachment)
            
        Returns:
            Dict containing the query execution result
            
        Raises:
            PermissionError: If user token is missing or doesn't have required permissions
            Exception: For other types of errors
        """
        if not self.user_token:
            error_msg = "User token is required to execute queries. Please log in."
            logger.error(error_msg)
            raise PermissionError(error_msg)
        
        # Get the SQL query if not provided
        if not query_text:
            try:
                # First get the attachment details to extract the SQL query
                attachment_url = f"{self.base_url}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}"
                self.update_headers(use_service_principal=True)  # Use service principal to get attachment details
                response = requests.get(attachment_url, headers=self.headers)
                response.raise_for_status()
                attachment_data = response.json()
                
                # Extract SQL query from attachment
                query_text = attachment_data.get("query", {}).get("query", "")
                if not query_text:
                    raise Exception("No SQL query found in attachment")
                    
            except Exception as e:
                logger.error(f"Error getting query from attachment: {str(e)}")
                raise Exception(f"Failed to get query from attachment: {str(e)}")
        
        logger.info(f"Executing SQL query: {query_text[:100]}...")
        
        # Execute query using Databricks SQL
        try:
            import os
            from databricks import sql
            
            # Get environment variables
            server_hostname = os.getenv("DATABRICKS_HOST")
            http_path = os.getenv("DATABRICKS_SQL_HTTP_PATH")
            
            if not (server_hostname and http_path):
                raise ValueError("DATABRICKS_HOST and DATABRICKS_SQL_HTTP_PATH environment variables must be set")
            
            # Use user token for SQL execution
            logger.info("Using user token for Databricks SQL execution")
            
            connection_params = {
                "server_hostname": server_hostname,
                "http_path": http_path,
                "access_token": self.user_token
            }
            
            # Add user context if possible
            try:
                import base64
                import json
                parts = self.user_token.split('.')
                if len(parts) >= 2:
                    payload_part = parts[1]
                    payload_part += '=' * (4 - len(payload_part) % 4)
                    decoded = base64.b64decode(payload_part)
                    token_data = json.loads(decoded)
                    user_email = token_data.get('email') or token_data.get('sub') or token_data.get('preferred_username')
                    if user_email:
                        connection_params["_user_id"] = user_email
                        logger.info(f"Adding user context to SQL connection: {user_email}")
            except Exception as e:
                logger.warning(f"Could not add user context to SQL connection: {e}")
            
            with sql.connect(**connection_params) as connection:
                cursor = connection.cursor()
                cursor.execute(query_text)
                
                # Get results
                result = cursor.fetchall()
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                
                # Convert to the expected format
                data_array = [list(row) for row in result]
                
                return {
                    "statement_response": {
                        "result": {
                            "data_array": data_array
                        },
                        "manifest": {
                            "schema": {
                                "columns": [{"name": col} for col in columns]
                            }
                        }
                    }
                }
                
        except Exception as e:
            logger.error(f"Error executing query via Databricks SQL: {str(e)}")
            if "403" in str(e) or "Forbidden" in str(e):
                error_msg = """
                Authentication Error: Invalid token scope.
                
                The provided token doesn't have the required permissions to execute SQL queries.
                This usually happens when the token is missing necessary OAuth scopes.
                
                Please ensure you're using a valid Databricks access token with the correct scopes.
                You may need to re-authenticate with the necessary permissions.
                """
                raise PermissionError(error_msg.strip())
            else:
                raise Exception(f"Failed to execute query via Databricks SQL: {str(e)}")
    

    def wait_for_message_completion(self, conversation_id: str, message_id: str, timeout: int = 300, poll_interval: int = 2) -> Dict[str, Any]:
        """
        Wait for a message to reach a terminal state (COMPLETED, ERROR, etc.).
        
        Args:
            conversation_id: The ID of the conversation
            message_id: The ID of the message
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
            
        Returns:
            The completed message
        """
        
        start_time = time.time()
        attempt = 1
        
        while time.time() - start_time < timeout:
            
            message = self.get_message(conversation_id, message_id)
            status = message.get("status")
            
            if status in ["COMPLETED", "ERROR", "FAILED"]:
                return message
                
            time.sleep(poll_interval)
            attempt += 1
            
        raise TimeoutError(f"Message processing timed out after {timeout} seconds")

def start_new_conversation(question: str, user_token: str = None) -> Tuple[str, Union[str, pd.DataFrame], Optional[str]]:
    """
    Start a new conversation with Genie.
    
    Args:
        question: The initial question
        user_token: User access token from X-Forwarded-Access-Token header
        
    Returns:
        Tuple containing:
        - conversation_id: The new conversation ID
        - response: Either text or DataFrame response
        - query_text: SQL query text if applicable, otherwise None
    """
    import logging
    logging.info(f"User token received: {user_token}")
    
    client = GenieClient(
        host=DATABRICKS_HOST,
        space_id=SPACE_ID,
        user_token=user_token
    )
    
    try:
        # Start a new conversation
        response = client.start_conversation(question)
        conversation_id = response.get("conversation_id")
        message_id = response.get("message_id")
        
        # Wait for the message to complete
        complete_message = client.wait_for_message_completion(conversation_id, message_id)
        
        # Process the response
        result, query_text = process_genie_response(client, conversation_id, message_id, complete_message)
        
        return conversation_id, result, query_text
        
    except Exception as e:
        return None, f"Sorry, an error occurred: {str(e)}. Please try again.", None

def continue_conversation(conversation_id: str, question: str, user_token: str = None) -> Tuple[Union[str, pd.DataFrame], Optional[str]]:
    """
    Send a follow-up message in an existing conversation.
    
    Args:
        conversation_id: The existing conversation ID
        question: The follow-up question
        user_token: User access token from X-Forwarded-Access-Token header
        
    Returns:
        Tuple containing:
        - response: Either text or DataFrame response
        - query_text: SQL query text if applicable, otherwise None
    """
    logger.info(f"Continuing conversation {conversation_id} with question: {question[:30]}...")
    
    client = GenieClient(
        host=DATABRICKS_HOST,
        space_id=SPACE_ID,
        user_token=user_token
    )
    
    try:
        # Send follow-up message in existing conversation
        response = client.send_message(conversation_id, question)
        message_id = response.get("message_id")
        
        # Wait for the message to complete
        complete_message = client.wait_for_message_completion(conversation_id, message_id)
        
        # Process the response
        result, query_text = process_genie_response(client, conversation_id, message_id, complete_message)
        
        return result, query_text
        
    except Exception as e:
        # Handle specific errors
        if "429" in str(e) or "Too Many Requests" in str(e):
            return "Sorry, the system is currently experiencing high demand. Please try again in a few moments.", None
        elif "Conversation not found" in str(e):
            return "Sorry, the previous conversation has expired. Please try your query again to start a new conversation.", None
        else:
            logger.error(f"Error continuing conversation: {str(e)}")
            return f"Sorry, an error occurred: {str(e)}", None

def process_genie_response(client, conversation_id, message_id, complete_message) -> Tuple[Union[str, pd.DataFrame], Optional[str]]:
    """
    Process the response from Genie
    
    Args:
        client: The GenieClient instance
        conversation_id: The conversation ID
        message_id: The message ID
        complete_message: The completed message response
        
    Returns:
        Tuple containing:
        - result: Either text or DataFrame response
        - query_text: SQL query text if applicable, otherwise None
    """
    # Check attachments first
    attachments = complete_message.get("attachments", [])
    for attachment in attachments:
        attachment_id = attachment.get("attachment_id")
        
        # If there's text content in the attachment, return it
        if "text" in attachment and "content" in attachment["text"]:
            return attachment["text"]["content"], None
        
        # If there's a query, execute it first then get the result
        elif "query" in attachment:
            query_text = attachment.get("query", {}).get("query", "")
            
            # First execute the query using user token (our new method)
            try:
                logger.info("Executing query using user token via Databricks SQL")
                client.execute_query(conversation_id, message_id, attachment_id, query_text)
                logger.info("Query execution completed successfully")
            except Exception as e:
                logger.error(f"Query execution failed: {str(e)}")
                return f"Query execution failed: {str(e)}", query_text
            
            # Then get the query result using service principal
            query_result = client.get_query_result(conversation_id, message_id, attachment_id)
           
            data_array = query_result.get('data_array', [])
            schema = query_result.get('schema', {})
            columns = [col.get('name') for col in schema.get('columns', [])]
            
            # If we have data, return as DataFrame
            if data_array:
                # If no columns from schema, create generic ones
                if not columns and data_array and len(data_array) > 0:
                    columns = [f"column_{i}" for i in range(len(data_array[0]))]
                
                df = pd.DataFrame(data_array, columns=columns)
                return df, query_text
    
    # If no attachments or no data in attachments, return text content
    if 'content' in complete_message:
        return complete_message.get('content', ''), None
    
    return "No response available", None

def genie_query(question: str, user_token: str = None) -> Union[Tuple[str, Optional[str]], Tuple[pd.DataFrame, str]]:
    """
    Main entry point for querying Genie.
    
    Args:
        question: The question to ask
        user_token: User access token from X-Forwarded-Access-Token header
        
    Returns:
        Tuple containing either:
        - (text_response, None) for text responses
        - (dataframe, sql_query) for data responses
    """
    try:
        # Start a new conversation for each query
        conversation_id, result, query_text = start_new_conversation(question, user_token)
        return result, query_text
            
    except Exception as e:
        logger.error(f"Error in conversation: {str(e)}. Please try again.")
        return f"Sorry, an error occurred: {str(e)}. Please try again.", None


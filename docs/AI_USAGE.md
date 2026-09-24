# AI Assistance Declaration

**Name:  Muhammad Usman**<br>
**Roll number:  25I-7605** <br>

## Tools used
I used Gemini for this Assignment. <br>
Link: https://share.gemini.google/9qHczCfDTVrb
## What I used them for
*   **Refactoring schemas:** Used generative AI to help structure the Pydantic models for the Validation and Approval layers to ensure strict type checking on LLM tool outputs.
*   **Debugging asynchronous execution:** Asked for explanations on why concurrent tool calls were blocking the main orchestrator loop.
*   **Test design:** Generated boilerplate mock responses and simulated telemetry timeouts to test the agent's exponential backoff and transient failure handling.
*   **Documentation:** Assisted in drafting the initial structure of the Markdown engineering reports and formatting the evaluation tables.

## Two suggestions I rejected or changed
1.  **Context Window Management:** The AI suggested appending raw `tool_result` string outputs directly to the system prompt for every step. I rejected this because it would rapidly lead to context window decay (a limitation I identified). I changed it to implement a summarized execution history that parses only the essential `evidence_id` and outcome before appending it to the state.
2.  **Tool Extraction Regex:** A coding assistant recommended using a complex Regex pattern to extract tool names and arguments from the LLM's raw text generation. I changed this to enforce native JSON structured outputs (using LangChain structured output parsers), which is far more reliable and avoids brittle regex parsing failures when the model hallucinates formatting.

## One AI-generated or AI-assisted bug I personally diagnosed
*   **Symptom:** During transient failure testing (like the simulated telemetry timeout in `public-b`), the orchestrator completely froze instead of executing the planned exponential backoff retries, locking up the entire runtime.
*   **Cause:** The AI assistant generated the retry logic using standard synchronous Python (`time.sleep(2)`) inside an `async def` orchestrator function. This blocked the entire `asyncio` event loop, preventing the agent from receiving further simulator observations or releasing resources.
*   **Fix:** I used a debugger to identify the blocked thread, diagnosed the synchronous blocking call, and replaced `time.sleep()` with `await asyncio.sleep()`. This correctly yielded control back to the event loop and allowed the backoff tiers (Initial, 2s, 10s) to execute non-blockingly.

## Code ownership statement
I can explain every submitted component, its failure behavior, and the trade-offs I chose. I understand that the TA may ask me to modify the code during viva.

Signature / typed name:  Muhammad Usman
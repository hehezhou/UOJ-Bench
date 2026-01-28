import requests
import json

from utils.call_llm import *
from utils.uoj_api import SubmissionRequest, Client
from utils.patch import *

prompt = """
You are an expert at fixing bugs in code. You will be given a buggy code and the complete description of the problem it intends to solve. Your job is to modify the code to make it correct while making as few changes as possible. The change must be expressed as a patch file that can be directly applied to the code using the patch command. Do not add any comments or explanations in the patch. Make sure your patch is minimal, i.e., the number of lines of code added or deleted is as small as possible. Enclose your patch within delimiters as follows.

```patch
# YOUR PATCH HERE
```

Here is an example of a patch file. It consists of changes to somean example code. It specifies the line numbers of each change, and the removed and added lines.

```patch
@@ -6,6 +6,6 @@
     int sum = 0;
     
-    for (int i = 0; i <= 5; i++) {{
+    for (int i = 0; i < 5; i++) {{
         sum += arr[i];
     }}
```


### Question:
{problem}

### Code:
{code}

### Answer: (use the provided format with backticks)


"""

try_again_prompt = "\nTry again! Output a new patch which would be directly applied to the code given for the first time."

import Levenshtein

def similarity(a: str, b: str) -> float:
    dist = Levenshtein.distance(a, b)
    max_len = max(len(a), len(b))
    return 1 - dist / max_len

def TestDebugAgent(model, problem_id, problem_statement, submission_code, submission_language='C++20', max_trials=10):
    submission_code = submission_code.replace('\r', '')
    # Initialize UOJ client
    client = Client()
    results=[]
    full_msgs=[]
    usages=[]
    counted_trials = 0
    message = prompt.format(problem=problem_statement, code=submission_code)
    message = [{"role": "user", "content": message}]
    while counted_trials < max_trials:
        try:
            # Make API request

            full_msgs.append(message[-1])

            assistant_message, full_msg, usage = call_llm_details(message, model)
            message.append({"role": "assistant", "content": '[REASONING]' + full_msg['reasoning_content']})
            message.append({"role": "assistant", "content": '[ANSWER]' + assistant_message})

            full_msgs.append(full_msg)
            usages.append(usage)

            # Extract patch between ```patch and ``` markers
            import re
            patch_match = re.search(r'```patch\n(.*?)```', assistant_message, re.DOTALL)
            if patch_match:
                patch = patch_match.group(1)
            else:
                message.append({"role": "user", "content": "No patch block found in your response" + try_again_prompt})
                counted_trials += 1  # counts as a trial
                continue

            # apply patch to code
            new_code = apply_patch_to_code(submission_code, patch)
            if similarity(new_code, submission_code) < 0.9:
                message.append({"role": "user", "content": "You made too many changes" + try_again_prompt})
                counted_trials += 1  # counts as a trial
                continue
            
            sub = SubmissionRequest(problem_id=problem_id, type='normal')
            sub.addSourceCodeText("answer", new_code, language=submission_language)

            result = client.makeBackgroundSubmission(sub)
            results.append(result)
            if 'result' in result and 'score' in result['result'] and result['result']['score'] == 100:
                return 1, message, results, full_msgs, usages
            else:
                message.append({"role": "user",
                                "content": f"The new code cannot pass all tests. Here is the results\n{result}\n\n" + try_again_prompt})
                counted_trials += 1  # counts as a trial
                continue

        except requests.exceptions.RequestException as e:
            print(f"Trial {counted_trials + 1} failed with request error: {e}")
            continue
        except json.JSONDecodeError as e:
            print(f"Trial {counted_trials + 1} failed with JSON parse error: {e}")
            continue
        except ValueError as e:
            counted_trials += 1  # counts as a trial
            message.append({"role": "user", "content": f"Meet error when applying patch: {e}" + try_again_prompt})
            continue
        except Exception as e:
            counted_trials += 1  # counts as a trial
            message.append({"role": "user", "content": f"Meet error {e}" + try_again_prompt})
            continue
    # If we get here, all trials failed
    return 0, message, results, full_msgs, usages

if __name__ == '__main__':    
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--file', type=str, default='dataset/small_submission_pairs.json', help='dataset file')
    parser.add_argument('--model', type=str, default="gpt-oss-120b", help='Model to use')
    parser.add_argument('--debug_idx', type=int, default=0, help='The index of debugging task that will be tested.')
    parser.add_argument('--max_trials', type=int, default=5, help='Max agent rounds.')
    args = parser.parse_args()

    with open(args.file, 'r', encoding='utf-8') as f:
        similar_codes = json.load(f)
    with open('dataset/problems.json', 'r', encoding='utf-8') as pf:
        _problems = json.load(pf)
        problems_by_id = {}
        for p in _problems:
            pid = p['problem_id']
            problems_by_id[pid] = p['statement_en']

    similar_code = similar_codes[args.debug_idx]
    problem_id = similar_code['problem_id']
    submission_id = similar_code['wrong_id']
    submission_code = similar_code['wrong_code']
    problem_statement = problems_by_id[problem_id]
    submission_language = similar_code['language']

    score, message, results, full_msgs, usages = TestDebugAgent(args.model, problem_id, problem_statement,
                                                                submission_code, submission_language,
                                                                args.max_trials)

    print(json.dumps({
        'debug_score': score,
        'results': results,
        'prompt': message,
        'full_msgs': full_msgs,
        'usages': usages,
    }, indent=2))

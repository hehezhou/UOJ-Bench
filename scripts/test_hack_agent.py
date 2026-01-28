import requests
import json

from utils.call_llm import *
from utils.uoj_api import SubmissionRequest, Client
from utils.patch import *

prompt = """
You are an expert at breaking buggy code. You will be given a buggy code and the complete description of the problem it intends to solve. Your task is to find a valid input, respecting the input format and constraints, that causes the code to fail (e.g., produces a Wrong Answer or exceeds the time limit).

Write a python program to print this failing test-case. Enclose your code within delimiters as follows.
```python
# YOUR CODE HERE
```

### Question:
{problem}

### Code:
{code}

### Answer: (use the provided format with backticks)

"""

try_again_prompt = "\nTry again! Output a new python code which would generate the correct hack data."

def TestHackAgent(model, problem_id, problem_statement, submission_code, submission_language='C++20', max_trials=10):
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
            if full_msg.get('reasoning_content', '') != '':
                message.append({"role": "assistant", "content": '[REASONING]' + full_msg['reasoning_content']})
                message.append({"role": "assistant", "content": '[ANSWER]' + assistant_message})
            else:
                message.append({"role": "assistant", "content": assistant_message})

            full_msgs.append(full_msg)
            usages.append(usage)

            # Extract code between ```python and ``` markers
            import re
            code_match = re.search(r'```python\n(.*?)```', assistant_message, re.DOTALL)
            if code_match:
                code = code_match.group(1)
            else:
                message.append({"role": "user", "content": "No Python code block found in your response" + try_again_prompt})
                counted_trials += 1  # counts as a trial
                continue
            
            sub = SubmissionRequest(problem_id=problem_id, type='hack')
            sub.addSourceCodeText("answer", submission_code, language=submission_language)
            sub.addHackInputText(code, language='Python3')
            sub.flagFormatInputFile() # auto-remove extra spaces in the input file

            result = client.makeBackgroundSubmission(sub)
            results.append(result)
            
            if 'result' in result and 'score' in result['result'] and result['result']['score'] == 1:
                return 1, message, results, full_msgs, usages
            else:               
                message.append({"role": "user",
                                "content": f"The python code generate invalid input or the code can still pass your test. Here is the results\n{result}\n\n" + try_again_prompt})
                counted_trials += 1  # counts as a trial
                continue
            
            # If we get here without exceptions, return successfully

        except requests.exceptions.RequestException as e:
            # Request errors (including 429) DO NOT count towards trials
            print(f"Trial {counted_trials + 1} failed with request error: {e}")
            time.sleep(20)
            continue
        except Exception as e:
            print(f"Trial {counted_trials + 1} failed with unknown error: {e}")
            counted_trials += 1  # counts as a trial
            message.append({"role": "user", "content": f"Meet error {e}" + try_again_prompt})
            continue
    # If we get here, all trials failed
    return 0, message, results, full_msgs, usages


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--file', type=str, default='dataset/hacks.json', help='dataset file')
    parser.add_argument('--model', type=str, default="gpt-oss-120b", help='Model to use')
    parser.add_argument('--hack_idx', type=int, default=0, help='The index of hack that will be tested.')
    parser.add_argument('--max_trials', type=int, default=5, help='Max agent rounds.')
    args = parser.parse_args()

    with open(args.file, 'r', encoding='utf-8') as f:
        hacks = json.load(f)
    with open('dataset/problems.json', 'r', encoding='utf-8') as pf:
        _problems = json.load(pf)
        problems_by_id = {}
        for p in _problems:
            if p['hackable']:
                pid = p['problem_id']
                problems_by_id[pid] = p['statement_en']

    hack = hacks[args.hack_idx]
    hack_id = hack['hack_id']
    submission_id = hack['submission_id']
    problem_id = hack['problem_id']
    submission_code = hack['wrong_code']
    submission_language = hack['language']
    problem_statement = problems_by_id[problem_id]

    score, message, results, full_msgs, usages = TestHackAgent(args.model, problem_id, problem_statement,
                                                               submission_code, submission_language,
                                                               args.max_trials)

    print(json.dumps({
        'hack_score': score,
        'results': results,
        'prompt': message,
        'full_msgs': full_msgs,
        'usages': usages,
    }, indent=2))
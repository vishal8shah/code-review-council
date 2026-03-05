# Code Review Council

<div class="hero">
  <p class="hero-tagline">AI reviews AI-generated code changes.</p>
  <p>
    <a class="hero-btn hero-btn-primary" href="getting-started/">Get Started</a>
    <a class="hero-btn" href="https://github.com/vishal8shah/code-review-council">View on GitHub</a>
  </p>
</div>

![AI is writing your code — who is reviewing it?](assets/infographics/hero-ai-writing-whos-reviewing.png)


## How it works

Code Review Council runs a five-stage pipeline:

1. **Gate Zero**: deterministic static checks.
2. **Diff** (preprocessing): filters noisy or generated changes.
3. **ReviewPack**: assembles structured context for reviewers.
4. **Panel**: specialist reviewers (SecOps, QA, Architect, Docs) analyze in parallel.
5. **Chair**: evidence-based synthesis and final recommendation.

![5-stage pipeline and two output modes](assets/infographics/pipeline-5-stage-two-outputs.png)


## Two outputs

- **Developer output**: technical findings with file/line evidence and rationale.
- **Owner output**: plain-English risk and impact summary with actionable next steps.

## Reality check / limitations

!!! warning "Use this as a quality gate, not a replacement for human review"
    - This is **not** a substitute for human engineering judgment.
    - Cost and latency vary by model selection, diff size, and concurrency.
    - BYOK secrets should be restricted and used only on branches/repositories you control.

## Try it in 60 seconds

```bash
git clone https://github.com/vishal8shah/code-review-council
cd code-review-council
pip install .
council init
council review --branch main
```

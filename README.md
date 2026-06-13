# Codeforces Virtual Coach

Codeforces Virtual Coach is a staged recommender-system project for competitive programmers. A user enters a Codeforces handle, the app analyzes their submission history, detects weak topics, and recommends unsolved problems that match their current growth needs.

## What It Does

- Fetches live Codeforces profile, submission, rating, and problemset data.
- Computes tag-wise accuracy, solved count, average solved rating, wrong-attempt pressure, activity cadence, strong topics, and weak topics.
- Recommends unsolved problems in the user's rating-growth band.
- Uses a Stage 2 content-based recommender with problem vectors, a user weakness vector, cosine similarity, and KNN.
- Produces a weekly training ladder with Core, Repair, Stretch, and Explore problems.

## Implemented Stages

### Stage 1: Analytics Engine

This is the non-ML foundation. It answers:

- What has the user solved?
- Which tags are strong?
- Which tags have low accuracy or low solved-rating depth?
- What rating range should the user practice next?

The backend computes:

- tag-wise attempted count
- tag-wise solved count
- tag-wise acceptance rate
- wrong attempts
- average solved rating
- max solved rating
- latest solve date
- weakness score

### Stage 2: Content-Based Recommender

Each problem is represented as a vector:

```text
[
  rating_scaled,
  rating_bucket,
  popularity,
  recency,
  tag=dp,
  tag=greedy,
  tag=graphs,
  tag=math,
  ...
]
```

The user is represented as a weakness/need vector:

```text
[
  target_rating,
  dp_weakness,
  greedy_weakness,
  graph_weakness,
  preferred_growth_band,
  ...
]
```

The app uses `sklearn` cosine similarity and KNN to score candidate problems, then blends that with the Stage 1 rule score.

## Final Ranking

```text
rule_score =
  0.40 * tag_weakness
+ 0.28 * difficulty_fit
+ 0.16 * popularity
+ 0.10 * undertrained_tag
+ 0.06 * retry_value

final_score =
  0.58 * rule_score
+ 0.34 * content_similarity
+ 0.08 * freshness
```

The final list is reranked with a diversity pass so the user does not get many near-identical problems from the same tag and rating band.

## Future Stages

### Stage 3: Collaborative Filtering

Mine cohorts of similar users and recommend problems commonly solved before rating jumps.

Possible techniques:

- user-problem matrix
- SVD
- ALS
- nearest-neighbor cohorts

### Stage 4: Rating Growth Prediction

Predict future rating from activity and weakness features.

Target:

```text
rating_after_30_days
```

Candidate models:

- Random Forest
- XGBoost
- LightGBM

### Stage 5: Learning-to-Rank

Train a ranking model for user-problem pairs.

Features:

- user rating
- problem rating
- rating gap
- tag match
- tag weakness
- problem popularity

Target:

```text
1 if solved / useful
0 otherwise
```

Candidate models:

- LightGBM Ranker
- XGBoost Ranker

## Tech Stack

- Backend: FastAPI
- Frontend: static HTML/CSS/JavaScript served by FastAPI
- Recommender: scikit-learn
- Cache: SQLite TTL cache
- Data: Codeforces API

## API Data Sources

The app uses official Codeforces API methods:

- `user.info`
- `user.status`
- `user.rating`
- `problemset.problems`

Reference: [Codeforces API methods](https://codeforces.com/apiHelp/methods)

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000`.

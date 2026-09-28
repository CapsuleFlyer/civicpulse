// Load generator for the HPA demonstration.
//
//   k6 run -e BASE_URL=http://localhost:8080 load/k6-script.js
//
// The profile is a step, not a ramp: capacity has to arrive *after* load does
// for the lag in question 5 of the engineering notes to be measurable at all.
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";
const submitLatency = new Trend("submit_latency_ms");

export const options = {
  scenarios: {
    read_load: {
      executor: "ramping-vus",
      exec: "browse",
      startVUs: 1,
      stages: [
        { duration: "30s", target: 5 },   // baseline: two pods are plenty
        { duration: "15s", target: 60 },  // the step: watch `kubectl get hpa -w`
        { duration: "3m", target: 60 },   // hold while replicas catch up
        { duration: "1m", target: 0 },    // release; scale-down is deliberately slow
      ],
    },
    write_load: {
      executor: "constant-arrival-rate",
      exec: "report",
      rate: 6,
      timeUnit: "1s",
      duration: "5m",
      preAllocatedVUs: 10,
      maxVUs: 40,
    },
  },
  thresholds: {
    // A zero-downtime rollout under load is the bonus item: run this during a
    // `kubectl set image` and this threshold is the evidence.
    http_req_failed: ["rate<0.01"],
    "http_req_duration{expected_response:true}": ["p(95)<2000"],
  },
};

const STREETS = ["G-9/1", "F-10/4", "I-8/2", "G-11/3", "H-13"];
const PROBLEMS = [
  "Water supply has not come since morning and the tanker is not available.",
  "Streetlight poles of the whole lane are off after maghrib.",
  "Garbage container has not been lifted for three days near the market.",
  "Big pothole has opened in the middle of the service road after rain.",
  "Transformer is making loud noise and sparking near the corner shop.",
];

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

export function browse() {
  const responses = http.batch([
    ["GET", `${BASE_URL}/api/complaints?page=1&page_size=10`],
    ["GET", `${BASE_URL}/api/stats`],
  ]);
  check(responses[0], { "queue is served": (r) => r.status === 200 });
  check(responses[1], { "stats are served": (r) => r.status === 200 });
  sleep(1);
}

export function report() {
  const body = JSON.stringify({
    // The timestamp defeats the content-hash cache on purpose: this scenario is
    // measuring the system under real triage work, not cache hits.
    text: `${pick(PROBLEMS)} Reference ${Date.now()}-${__VU}.`,
    location: `Street ${Math.ceil(Math.random() * 40)}, ${pick(STREETS)}, Islamabad`,
  });
  const response = http.post(`${BASE_URL}/api/complaints`, body, {
    headers: { "Content-Type": "application/json" },
  });
  submitLatency.add(response.timings.duration);
  // 429 is a correct answer under load, not a failure of the system.
  check(response, { "accepted or rate limited": (r) => r.status === 201 || r.status === 429 });
}

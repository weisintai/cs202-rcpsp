1. Project Technical Details
What problem did we investigate?
When many people use a website at the same time, a load balancer sits in front of the servers and decides which one handles each visitor's request. If that decision is made poorly, some servers get overwhelmed while others sit idle, and users see slow pages, timeouts, or errors. As queues grow, average waiting time rises [1], and even one slow server can hurt the overall user experience [2]. We therefore wanted to find out which combination of traffic-routing rules and overload safeguards keeps a website fastest and most reliable under realistic stress.
Why we chose these variables
We focused on three things a system administrator can change without rewriting application code. The first was the routing algorithm: round-robin or least-connections. Queue-aware routing can change how evenly work is shared when load is uneven [3], [6]. The second was the overload policy: unlimited forwarding or a 30-connection cap per server. This choice affects whether excess traffic turns into long waits or fast rejection [3], [4], [5]. The third was the number of backend servers, scaling from 1 to 10 on one host. These are common decisions when configuring a load-balanced web service [3].
How we tested it
We used HAProxy in front of lightweight web servers, each limited to roughly half a CPU core and 0.2 GB of memory. Every request included a simulated 50-millisecond processing delay. We generated traffic using a command-line load-testing tool and aimed for 10 repeats per condition, then computed averages with 95% confidence intervals from the successful runs.
Experiments 1 to 3 used the normal backend setup. This let us study scaling out, slow-server behaviour, and burst traffic under typical service conditions. Experiment 4 used a tighter single-worker, single-threaded backend setup to create a clear overload limit. That made it easier to compare unlimited forwarding against connection capping under controlled saturation. We then ran four experiments:
Experiment 1 (Scale-out): 50 simulated users sent requests to the service for 20 seconds. We compared a single backend with clusters of 3, 5, and 10 backend servers on one host (Figure 1).

Figure 1. Direct routing (top) versus cluster routing through HAProxy (bottom).
Experiment 2 (Straggler): 60 users sent requests to a three-backend cluster for 30 seconds, while one backend was deliberately weakened by adding extra delay and reducing how much work it could handle at once (Figure 2). We compared round-robin against least-connections to see which policy handled the uneven cluster better.

Figure 2. Straggler and burst setup: one backend (web3) is artificially delayed.
Experiment 3 (Burst): 10 steady users sent requests to a healthy three-backend cluster for 30 seconds, while an additional burst of 200 requests arrived at the 5-second mark, simulating a flash-sale scenario. We again compared round-robin against least-connections to see which policy better protected existing users during a sudden spike.
Experiment 4 (Overload): 1200 simulated users sent requests to the service for 20 seconds, enough to push the cluster well past its safe limit. Using the tighter backend setup, we compared unlimited forwarding against a 30-connection cap per server.
What we found
Experiment 1: Adding backend replicas helps on one host

Figure 3. Throughput and latency across backend replicas.
Adding backend servers consistently improved performance across the full range we tested. Throughput rose from 74 requests per second on a single backend to 226 with 3 servers, 380 with 5, and 615 with 10, while average latency fell from 660 ms to 81 ms (Figure 3). Scaling from 1 to 10 servers therefore delivered both higher throughput and faster responses on the shared host.
Experiment 2: Least-connections handles a slow server better

Figure 4. P95 latency and throughput under straggler conditions.
When one server slowed down, round-robin continued sending it the same share of traffic as the healthy servers, forcing many users to wait behind the bottleneck. Least-connections responded better by shifting more work away from the overloaded server. This matches earlier findings that slow servers can disproportionately hurt overall performance [2]. In our experiment, it cut average latency from 1034 ms to 359 ms, reduced the response time for the slowest 5% of requests from 3134 ms to 1062 ms, and raised throughput from 55 to 150 requests per second (Figure 4). For users, that means far fewer severe slowdowns when one backend starts struggling.
Experiment 3: Spike protection for steady users

Figure 5. Average latency and throughput during a 200-request burst at t = 5 s.
During a sudden traffic spike, least-connections again outperformed round-robin (Figure 5). The HAProxy manual states that least-connections chooses the server with the fewest active connections and also considers queued connections [3]. Earlier work on web-service load balancing also suggests that queue-aware routing can reduce waiting overhead under heavier load [6]. In our experiment, this spread the burst more evenly and better protected the 10 steady users from congestion. During the burst, average latency fell from 73 ms under round-robin to 66 ms under least-connections, while throughput rose from 126 to 152 requests per second. This matters in events such as flash sales or viral content spikes, where existing users can otherwise be slowed down by a sudden wave of new requests.
Experiment 4: Under overload, the cap fails more cleanly

Figure 6. Request outcomes and latency under overload, with and without a connection cap.
When traffic went far beyond what the cluster could handle, unlimited forwarding led to long waits and many client timeouts (Figure 6). Across the successful overload runs, it completed about 1128 successful requests and produced about 1198 transport timeouts. In other words, many requests waited so long that the client gave up. Average latency was about 10.1 s. With the 30-connection cap, the system completed more successful requests on average (1493), produced no transport timeouts, and rejected excess traffic with explicit 503 responses instead. Average latency also fell to about 5.3 s. The cap does not remove overload, but it turns unclear hanging failures into faster and more explicit rejection. This matches earlier work showing that limiting requests during overload can make failures more predictable and easier to handle [3], [4], [5].
Summary of findings
Experiment
What counts as best
User impact
Winner
1: Scale-out
Higher throughput, lower latency, practical resource use
Shorter page loads under normal traffic
10-replica cluster
2: Straggler
Lower worst-case delays when one server becomes slow
Fewer severe slowdowns
Least-connections
3: Burst
Steady-user latency stays low during spikes
Existing users protected from flash crowds
Least-connections
4: Overload
Fewer timeouts and faster rejection during overload
Fast rejection instead of hanging requests
30-connection cap

Conclusions
In our test environment, the clearest single change was switching from round-robin to least-connections when servers were uneven or traffic spikes were expected. A second useful change was adding a connection cap. It did not remove overload, but it turned long client timeouts into faster and clearer rejection once the system was full [3], [4], [5]. Scaling out also helped, improving both throughput and latency all the way to 10 backend servers on one host. Taken together, our results suggest that routing policy and overload policy solve different problems, so a practical setup should consider both.
Limitations
Our servers ran a lightweight Python application with a simulated 50 ms request cost. Production services with multi-threaded frameworks, database calls, or heavier request handling may respond differently. The slow-server condition was simulated with artificial delay, which does not cover all real-world failure modes such as memory leaks or disk contention. We tested only one type of request and one workload pattern per experiment. Only a single load-balancer instance was used, so backup load balancers and failover setups remain untested. Finally, the overload experiment showed timeouts and 503 responses rather than hard process crashes, so comparing behaviour under actual server crashes would require further work. Because Experiment 4 used a tighter backend setup than Experiments 1 to 3, its results should be read as a controlled overload study rather than a direct extension of the earlier tests.
2. Project Management Overview
Who did what
Tew Zhe Khai automated the testing pipeline to ensure consistent, repeatable runs across all configurations. Tai Wei Sin configured the load balancer’s routing rules and connection limits. Tan Eu-Joe managed backend server environments and resource allocation. Htet Shwe Win Than synthesised findings and drafted the report. Aung Ye Thant Hein analysed test data and produced the charts and summary statistics.
What went well
The fully automated 10-run pipeline worked reliably across all experiment configurations, including the extended scale-out scenarios (1, 3, 5, and 10 replicas). Visual outputs were regenerated directly from the current runs, ensuring that every figure in this report matches the actual data. This kept the analysis reproducible and consistent.
What did not go well, why, and how we fixed it
Keeping experiments consistent across an expanded test matrix. As we added scale-out configurations, discrepancies crept in between the automation scripts and the report’s figure references. We resolved this by centralising the experiment list in one analysis script and regenerating all figures from that single source of truth.
Supporting the maxconn claim with the right evidence. After finishing Experiment 4, we realised that our claim about maxconn making the system safer was still too vague. We had observed better behaviour, but we had not yet decided which numbers would prove it clearly. We fixed this by defining concrete measures, including timeout counts, successful requests, latency, and 503 responses, and then using those numbers to support the final argument.
Long runtime for repeated experiments. The full 10-run batches took a long time to complete, which slowed iteration and made each rerun costly. This made it harder to test changes quickly, especially late in the project. We handled this by being more selective about reruns and reserving the full 10-run sets for configurations that were already stable enough for final analysis.
References
[1] J. D. C. Little, "A proof for the queuing formula: L = λW," Operations Research, vol. 9, no. 3, pp. 383-387, 1961, doi: 10.1287/opre.9.3.383.
[2] J. Dean and L. A. Barroso, "The tail at scale," Communications of the ACM, vol. 56, no. 2, pp. 74-80, 2013, doi: 10.1145/2408776.2408794.
[3] HAProxy Technologies, “HAProxy configuration manual version 3.2,” 2026. [Online]. Available: https://docs.haproxy.org/3.2/configuration.html. [Accessed: Mar. 10, 2026].
[4] M. Welsh and D. Culler, "Adaptive overload control for busy Internet servers," in Proc. 4th USENIX Symp. Internet Technologies and Systems (USITS), Seattle, WA, USA, Mar. 2003, pp. 43-57. [Online]. Available: <https://www.usenix.org/event/usits03/tech/full_papers/welsh/welsh.pdf>. [Accessed: Mar. 28, 2026].
[5] I. Cho, A. Saeed, J. Fried, S. J. Park, M. Alizadeh, and A. Belay, "Overload control for μs-scale RPCs with Breakwater," in Proc. 14th USENIX Symp. Operating Systems Design and Implementation (OSDI), Nov. 2020, pp. 299-314. [Online]. Available: <https://www.usenix.org/system/files/osdi20-cho.pdf>. [Accessed: Mar. 28, 2026].
[6] Y. Lu et al., "Join-idle-queue: A novel load balancing algorithm for dynamically scalable web services," Performance Evaluation, vol. 68, no. 11, pp. 1056-1071, 2011, doi: 10.1016/j.peva.2011.07.015.

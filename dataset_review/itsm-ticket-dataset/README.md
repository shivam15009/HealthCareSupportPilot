# Synthetic ITSM Helpdesk Ticket Dataset

A dataset intended to be explored to surface business problems that may be solved in modelling projects or as recommendations in case studies

## What is in this repository

- merchants.csv, 112 merchant accounts
- agents.csv, 20 support agents
- tickets.csv, just over two thousand tickets spanning eighteen months of history plus a live open queue

## Schema

### merchants.csv

| Column | Description |
|---|---|
| merchant_id | Numeric identifier |
| merchant_name | Generated company name |
| sector | Industry sector |
| tier | Advanced or Foundation, reflects account volume |
| region | Operating region |

### agents.csv

| Column | Description |
|---|---|
| agent_id | Numeric identifier |
| agent_name | Agent name |
| tier | L1, L2 or L3 support level |
| primary_category | The ticket category this agent specialises in |
| shift_region | Region the agent's shift covers |
| efficiency_multiplier | A persistent per agent performance factor that shapes response and resolution time |

### tickets.csv

| Column | Description |
|---|---|
| ticket_id | Numeric identifier |
| merchant_id | Foreign key to merchants |
| category, sub_category | Ticket classification |
| priority | P1 to P4 |
| created_at | Ticket creation timestamp |
| is_legacy | Whether the ticket belongs to the historical batch rather than the live open queue |
| assigned_agent_id | Foreign key to agents, blank for new tickets still awaiting routing |
| category_mismatch | Whether the assigned agent's specialty differs from the ticket category |
| first_response_at, closed_at | Response and resolution timestamps |
| ttfr_hours, resolution_hours | Duration metrics in hours |
| response_breached, resolution_breached | Breach flags against SLA targets tied to priority |
| is_reopened | A probability driven outcome, built entirely from intake time features |
| is_reopen_child | Whether the record is the escalated follow up spawned by a reopen |
| is_incident_ticket | Whether the ticket was generated or affected by one of three simulated platform incidents |
| csat_score | Present for roughly one in eight closed tickets, reflecting realistic survey non response |

New tickets carry blank values in several columns, including first_response_at, closed_at and csat_score. This is by design, since these tickets have not been processed yet, not a sign of missing or broken data.

## How to use it

Works in whatever tool you use. Load the CSVs into Python, R or a SQL database and query, model or visualise from there. No dependency on any particular language or platform.

## Project ideas

A ticket routing model is the one currently in progress. Comparing how well tickets are handled before and after automated routing is a natural next step once that exists. Predictive modelling of customer satisfaction is a further direction, useful in its own right and as something that could feed into the routing work.

## Known issues and feedback

This is the first iteration of my first synthetic dataset. I would be grateful for any feedback that identifies problems or suggestions

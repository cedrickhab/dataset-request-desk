# REST contract
Prefix /api, JSON, UUID IDs, ISO UTC timestamps, counts integers, duration as decimal string. Session cookie authentication; CSRF unsafe methods. Errors {error:{code,message,fields?},request_id}. 400validation,401unauthenticated,403forbidden,404inaccessible/not found,409workflow/allocation conflict,413upload too large,429throttled,503health DB unavailable. Lists {count,next,previous,results}; page_size default25 max100, stable created_at/id ordering. Never serialize password hash, cookies or secrets.

| Method/path | Allowed | Body/result |
|---|---|---|
| GET /auth/csrf | Anonymous login setup exception | CSRF token/cookie |
| POST /auth/login | Anonymous, CSRF required | email,password -> user |
| POST /auth/logout | All active users | invalidate session,204 |
| GET /auth/me | All | id,name,email,role |
| GET /requests | Client own; staff all | status/task filters, counts |
| POST /requests | Client | task_name,episodes_requested,deadline,notes ->201 |
| GET /requests/{id} | Owner/staff | request,assigned_count,allowed_actions |
| GET /requests/{id}/history | Owner/staff | actor name/id,time,old/new status |
| POST /requests/{id}/transitions | Step-specific | status,optional reason ->updated request |
| GET /episodes | Staff | task_name,quality,available,page |
| POST /episodes/import | Staff | multipart file ->summary/issues |
| GET /requests/{id}/assignments | Owner/staff | episode metadata + export status |
| POST /requests/{id}/assignments | Staff | episode_ids UUID array -> links/count |
| DELETE /requests/{id}/assignments/{id} | Staff,in_progress |204 |
| GET /analytics | Staff | start,end ->aggregates |
| GET /users | Admin | users paginated |
| POST /users | Admin | name,email,password,role,organisation? ->201 |
| PATCH /users/{id} | Admin | role and/or is_active ->user |
| GET /health (outside prefix) | Authenticated |200ok/503unavailable |

Example request POST {"task_name":"pick cup","episodes_requested":2,"deadline":"2026-10-04","notes":"Clear view of cup"}. Response includes server owner/status submitted; no invented client_id accepted. Assignment response includes existing/new IDs, assigned_count and episodes_requested. allowed_actions calculated server-side for user and state, e.g. ["start_work"] or ["assign","deliver"] only when eligible. UI still handles server conflicts because state can change after response.
CSV report {processed:190,imported:0,skipped:190,...} is illustrative, NOT actual seed totals. Agent must use executed totals in final docs. OpenAPI schema generated from implemented serializers must match this contract; expose schema/docs to authenticated users only.

# Keystore section lifecycle review — 2026-10-04

This follows the remaining lifecycle question from the
[utility review PR #12](https://github.com/decryptus/sonicprobe/pull/12).
The change is independent of that PR, XYS #10 and network #11.

## Reproduced failures

1. `acquire(name); delete(name); set(name, key, value); release(name)` replaced an
   owned section lock. The release targeted an unowned new lock and raised; another
   thread could acquire the replacement while the first owner was still active.
2. `acquire(name, blocking=False, exists=True)` performed a blocking existence
   check first and could wait for another owner, then return True after release.
3. An operation waiting on a section lock could wake after deletion and access
   removed data. Removing a missing section key with `lock=False` could create an
   update timestamp with no corresponding data/lock.
4. Global ownership and outstanding explicit section ownership were coordinated
   separately. A global owner could wait for a section whose owner needed the
   global gate to finish its work: a lock-order inversion.

## Coordination model

A per-instance condition protects section data, timestamps, owner counts and
waiter counts. Ordinary dictionary operations are serialized inside this short
critical section. The condition releases its mutex while waiting for ownership;
no thread holds it while blocking on another thread's section RLock.

Each section name keeps the same reentrant lock while it has data, an owner or a
waiter. Deletion removes the data and timestamp. The lock disappears only after
all owners/waiters have left and no data has been recreated. This avoids both
stale replacement locks and an ever-growing registry of deleted names.

A global lock can be obtained only when there are no section owners from other
threads. Pending global requests prevent new unrelated operations from overtaking
indefinitely; existing section owners can still finish and release. No strict FIFO
or starvation bound is promised. All ownership is reentrant and thread-specific.

## Public contracts and compatibility changes

| Operation | Behavior |
| --- | --- |
| `acquire(name, blocking=False)` | No waiting on existence checks, global ownership or the metadata mutex; False if unavailable |
| `try_acquire(name, timeout)` | One elapsed-time budget includes metadata/global/section contention; True, None if missing with `exists=True`, otherwise historical False/0 failure values |
| `acquire(name)` | Blocking section acquisition; configured `Keystore.timeout` still bounds initial global/metadata entry |
| `delete(name)` | Respects section ownership by default; a current owner can delete and recreate its own section without losing ownership |
| `delete(name, lock=False)` | Explicitly bypasses section exclusion, but preserves outstanding owners and atomic metadata transitions |
| `exists=True` waiter | Rechecks existence after wake-up; cannot report ownership of an absent section |
| `get(..., lock=True)` waiter | Returns the supplied default if the section was deleted while waiting |
| `set(..., lock=True)` waiter | Recreates absent data after obtaining section ownership |
| `lock()` with other threads owning sections | Waits until those owners finish; they remain able to operate and release |
| `lock()` while already owning a section and other threads also own sections | Returns None immediately to avoid circular promotion waits; `try_lock` uses its existing False/0 failure conventions; existing ownership is retained |
| `remove` on a missing section | Raises KeyError consistently for either lock flag; no timestamp-only section is created |
| `lock=False` data operations | Still opt out of section exclusion; metadata coherence does not make a sequence of calls an atomic transaction |

Callers must check lock acquisition results and use `finally` to release successful
acquisitions. Prefer acquiring global ownership before section ownership if both
are needed. The `lock` argument on `acquire` remains accepted; the redundant
blocking precheck has been removed.

The invalid-input tests for nonblocking acquisitions now verify immediate failure
under contention. Their previous expectation that nonblocking calls wait behind a
global lock contradicted the corrected contract. Blocking-operation error cleanup
checks remain unchanged.

Monotonic time is used where available; Python 2 retains the wall-clock fallback.
Timestamp/expiration APIs remain wall-clock based. Snapshot iterators, chainable
methods and missing-section conventions are preserved except the documented
`remove` correction.

## Verification and limits

Tests coordinate real threads with events and verify recursive owners, deletion
and recreation, waiting readers/writers, interrupted waits, timeout cleanup,
competing global waiters, ownership errors and bounded lock-record retention.
Existing concurrency tests and consumer suites are also run; results are recorded
in the PR, including installed-package and combined-candidate checks.

DWho constructs this object as runtime shared storage; NSAProxy's
`try_acquire(name, timeout, exists=False)` / `release(name)` pattern is covered by
the existing integration test. This does not certify every external plugin.

The coordination change serializes short dictionary operations. No throughput
claim is made for high-contention/free-threaded workloads. User-defined key hashing
or equality runs as part of dictionary operations and should not perform blocking
cross-thread work. Values remain caller-owned mutable objects; the store does not
synchronize mutations performed directly on returned values. Thread termination
while owning a lock and arbitrary cross-section lock-order cycles are not repaired
automatically. These tests are not a formal proof over every possible interleaving.

No release, publication or deployment is part of this review.

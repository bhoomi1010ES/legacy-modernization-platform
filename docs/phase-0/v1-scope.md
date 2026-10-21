# V1 Scope Specification: Multi-Agent Legacy Code Modernization Platform

**Document:** `docs/phase-0/v1-scope.md`  
**Phase:** Phase 0 (Discovery, Scope & Architectural Foundation)  
**Date:** October 19, 2026  
**Status:** Completed  
**Author:** Principal Software Architect & Multi-Agent Systems Architect  

---

## 1. Selected V1 Vertical Slice Stack Pair

### 1.1 Stack Selection `[OPEN_DECISION - Recommended Default]`
- **Legacy Source Stack:** **Java 8 – 17 / Spring Boot 2.x (MVC & REST)**
- **Target Modern Stack:** **TypeScript 5.x / Node.js 22 LTS / NestJS 10.x**

### 1.2 Rationale & Tooling Readiness
1. **Structural Isomorphism:** Both Spring Boot and NestJS follow the modular, decorator-driven architecture pattern (`@Controller`, `@Service`, `@Repository`, `@Injectable()`), enabling deterministic structural and dependency mappings.
2. **Robust Analysis Ecosystem:** High-fidelity Abstract Syntax Tree (AST) tools exist for Java (Tree-sitter, JavaParser, OpenRewrite) that permit static extraction of endpoint routes, entity models, and business logic without running arbitrary untrusted code.
3. **High Industry Demand:** Modernizing legacy monolithic enterprise Java services into maintainable TypeScript microservices or modular monoliths is one of the highest-volume migration initiatives in software engineering.

*Note:* Alternative target stacks (e.g. Python / FastAPI or Go / Gin) are defined as extension profiles in the catalog, but V1 focuses on this single vertical slice to guarantee high behavioral equivalence.

---

## 2. Supported Scope & Capabilities

### 2.1 Supported Repository Structures
- **Repository Types:** Git repositories (public or private with authorized deploy key) and uploaded `.zip` / `.tar.gz` archives up to 250 MB.
- **Project Structure:** Single-module or multi-module Maven (`pom.xml`) and Gradle (`build.gradle`) standard directory layouts (`src/main/java`, `src/main/resources`, `src/test/java`).
- **Code Limits:** Up to 150,000 lines of Java source code per modernization job.

### 2.2 Supported Database & Persistence Technologies
- **Relational Databases:** PostgreSQL 13–16, MySQL 8.x, Oracle Database (standard ANSI SQL queries).
- **ORM / Persistence:** Spring Data JPA, Hibernate entity mappings, and MyBatis/JDBC standard repository interfaces.
- **Target Schema Generation:** Prisma or TypeORM migrations with standard PostgreSQL dialect.

### 2.3 Supported Conversion Capabilities
1. **REST API Controllers:**
   - Spring `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@DeleteMapping`.
   - Path parameters (`@PathVariable`), query parameters (`@RequestParam`), and JSON request/response bodies (`@RequestBody`).
   - Standard HTTP status code representations (`ResponseEntity<T>`).
2. **Business Services & Dependency Injection:**
   - Stateless services (`@Service`, `@Component`).
   - Constructor and field dependency injection refactored to NestJS constructor injection.
3. **Data Transfer Objects (DTOs) & Validation:**
   - Java POJOs / Records converted to TypeScript classes with `class-validator` and `class-transformer` decorators.
4. **Data Entities & Repositories:**
   - JPA entity annotations (`@Entity`, `@Table`, `@Id`, `@Column`, `@ManyToOne`, `@OneToMany`) mapped to NestJS repository entities.
5. **Characterization Tests:**
   - Unit test capture, API contract replay, and golden fixture validation using Vitest/Jest against NestJS controllers.

---

## 3. Known Limitations & Explicitly Unsupported Features

### 3.1 Explicitly Unsupported Features `[OUT_OF_SCOPE for V1]`
1. **Server-Side Rendered (SSR) Legacy UI:** JSP (JavaServer Pages), JSF (JavaServer Faces), Thymeleaf, Struts, and Velocity templates. (V1 modernizes APIs and backend services only).
2. **Desktop & Native Bindings:** Swing, JavaFX, AWT, JNI (Java Native Interface), COM interop.
3. **Complex Distributed Transactions:** Two-phase commit (XA transactions), JTA coordinators, WS-AtomicTransaction.
4. **Proprietary Legacy Middleware:** WebLogic/WebSphere-specific deployment descriptors, EJB 2.x remote entity beans, RMI-IIOP.
5. **Complex Batch & Legacy Messaging:** Native IBM MQ, TIBCO Rendezvous, SOAP RPC-encoded web services (SOAP requires an explicit G1 gap decision adapter).

### 3.2 Expected Platform Behavior for Unsupported Input
When an unsupported construct is encountered:
- The **Intake** and **Legacy Analyzer** agents flag the file, line number, and AST construct.
- The construct is recorded in the `CapabilityCoverage` schema as `Unsupported` or `Gap`.
- At **Gate G1 (Feasibility)**, the platform halts automated conversion and presents the findings to the human reviewer with options:
  - *Adapter:* Wrap the legacy boundary in a dedicated micro-proxy.
  - *Descope:* Exclude the capability from the modernized service.
  - *Hand-fix:* Provide manual guidance or code.
- Under no circumstance does the platform silently omit or corrupt unsupported business logic.

---

## 4. Conditions for Job Acceptance and Rejection

### 4.1 Acceptance Criteria
A modernization job is accepted into the `Analyzing` lifecycle stage only if:
- [x] The repository URL is reachable, or the source archive unpacks without corruption.
- [x] At least one valid build descriptor (`pom.xml` or `build.gradle`) is detected at the root or declared module path.
- [x] Java source code is present (`.java` files constitute >= 60% of source files).
- [x] The job budget is >= $50.00 USD (minimum allocation required for multi-pass analysis).
- [x] Maximum repair attempts parameter is configured between 1 and 5 (default: 3).

### 4.2 Rejection Criteria
A job is immediately rejected during Intake if:
- Source repository contains unencrypted binary executables (`.exe`, `.dll`, `.so`) or encrypted archives.
- The repository exceeds 250 MB compressed or 150,000 lines of code (requiring enterprise batch decomposition).
- No recognized Java entry points or build files exist.
- Malicious shell scripts, suspicious network egress calls, or path traversal attacks are detected during intake scanning.

---

## 5. Smallest Demonstrable Modernization Workflow (V1 Vertical Slice)

The minimum end-to-end slice proves the core value hypothesis:
```text
[Legacy Java Customer Service]
          │
          ▼
   1. Intake & Parse AST (pom.xml, CustomerController.java, CustomerService.java)
          │
          ▼
   2. Gate G1: Human confirms 100% native capability coverage
          │
          ▼
   3. Characterize: Capture 12 legacy behavioral tests & golden JSON responses
          │
          ▼
   4. Gate G2: Human freezes characterization test baseline
          │
          ▼
   5. Blueprint: Decompose into NestJS AppModule, CustomerModule, CustomerService
          │
          ▼
   6. Gate G3: Human approves target architecture & wave plan
          │
          ▼
   7. CodeWriter: Generate TypeScript / NestJS source files in sandboxed branch
          │
          ▼
   8. Verifier: Replay frozen tests against NestJS service -> 100% equivalence
          │
          ▼
   9. Gate G4: Human inspects verification report & authorizes delivery pull request
          │
          ▼
[Verified Modernized NestJS Service]
```

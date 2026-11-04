# W00 Read-Only State Summaries (Pre-Remediation Freeze)

> **Capture Time:** 2026-10-30T05:34:55.969232+00:00  
> **Source Database:** `rebase` (PostgreSQL 18 on localhost:5432)  
> **Isolation Guarantee:** Executed in pure read-only transactions with zero mutations.  

## 1. Job Counts by State

| Status | Count |
|---|---:|
| `FAILED` | 1,653 |
| `CREATED` | 427 |
| `AWAITING_GATE_G1` | 182 |
| `AWAITING_GATE_G2` | 104 |
| `CANCELLED` | 80 |
| `AWAITING_GATE_G3` | 25 |
| `COMPLETED` | 21 |
| `AWAITING_GATE_G4` | 12 |
| `ANALYZING` | 9 |
| `CONVERTING` | 4 |
| `PAUSED` | 1 |
| **Total Jobs** | **2,518** |

### Active Jobs with Missing / Expired Orchestration Leases

- Total active (non-terminal) jobs: **764**
- Active jobs with expired/missing lease: **764**

| Job ID | Name | Status | Owner | Lease Expires At | Updated At |
|---|---|---|---|---|---|
| `44ac6de1-55fc-4dd8-99cb-baf343d1d742` | `supervisor-e2e-a4f65e16` | `AWAITING_GATE_G2` | `supervisor:1942bce2cde8451da4725981d98a1923` | `2026-10-26 08:47:08.187752+00:00` | `2026-10-26 08:42:59.390856+00:00` |
| `a1076c96-965d-4a3a-b028-0364802c84ad` | `phase3-e5a2e3d9-cbf9-49b4-9f84-76f7d8cc58bd` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:00.877425+00:00` |
| `6a7d6434-bc8a-4611-9c20-41c0e3c8774c` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-27 06:06:23.459478+00:00` |
| `368a699c-1621-4e00-a405-b42bd51314d8` | `supervisor-e2e-5e66d17d` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 06:33:32.509230+00:00` |
| `fbb8918a-6a98-4ffe-9980-f819d2f67358` | `phase3-8fdc53dd-6e67-494b-bd10-cd050fa7fe86` | `AWAITING_GATE_G2` | `supervisor:ad7878451e7840b78711c84946505561` | `2026-10-26 09:09:29.476817+00:00` | `2026-10-26 09:05:49.460350+00:00` |
| `9c529174-2fb2-4f69-a39d-e758dcbe3ec3` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-28 11:32:52.738104+00:00` |
| `18accde1-3e62-4f9e-8e0e-afe188887317` | `phase3-compliance-2f0ee86d` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 08:51:07.040775+00:00` |
| `5512a921-95c6-4d3e-b0de-d44189248e99` | `supervisor-e2e-dad362a8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:52:15.586666+00:00` |
| `fe9a2b75-9351-467a-a46e-5a22a8569680` | `phase3-7da7cc68-595b-430b-a2f4-ddfd575ada0c` | `CREATED` | `None` | `None` | `2026-10-26 11:18:41.664116+00:00` |
| `6e9ac849-1877-4542-8adf-920269247764` | `test-p4-p5-d3433f` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 11:06:52.201417+00:00` |
| `536e1204-6447-453f-9592-48e0720f3655` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-27 06:06:24.273924+00:00` |
| `cef9728e-d2e1-47b8-bbbf-e6938adbc3bc` | `test-p4-p5-8248cf` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 12:15:34.777582+00:00` |
| `21c3eb6f-cf0c-4a3a-831f-1aac5d855d6f` | `phase3-fe0549e2-8515-40d9-a349-5d009f9e471d` | `CREATED` | `None` | `None` | `2026-10-22 06:25:24.506732+00:00` |
| `3c66741c-4d6f-44e4-829d-d2a6f0f194a2` | `phase3-6f06f754-34a6-4275-b9b2-c595a37c5597` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 09:34:25.961477+00:00` |
| `f8f16371-cbf3-4cf9-97b9-1821ad4224d4` | `phase3-c7591cc8-409c-4da2-8d39-256213590955` | `CREATED` | `None` | `None` | `2026-10-26 11:19:28.411004+00:00` |
| `547c1f28-7d70-4d5f-bb32-1d697f44f063` | `supervisor-e2e-e2fb6ca8` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 08:51:08.007533+00:00` |
| `cb528ac8-48ca-4104-880e-046040e8e1f2` | `phase3-compliance-17159a2c` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 09:05:36.722459+00:00` |
| `7763014c-4320-4b69-967d-d728c1b8c446` | `neg-empty-3a110d` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:06:52.164045+00:00` |
| `1257433d-98d6-4643-9c9b-50f4d1707d12` | `test-p4-p5-2a9d4b` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:52:23.514075+00:00` |
| `3b41bf12-4afc-4e1c-8d6b-f6243ee9199c` | `supervisor-e2e-82b6898d` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 06:33:54.130104+00:00` |
| `5d0caafa-7b6c-4f51-8481-f5896b31bb68` | `neg-empty-49036f` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:43:26.428955+00:00` |
| `a7b321d7-28b1-4fc2-a209-7ac8bb9226ef` | `supervisor-e2e-ea8e03a7` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:50:53.951930+00:00` |
| `d2be81a2-517b-4ca5-a3e5-147296931558` | `neg-untested-663d5c` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:06:52.159342+00:00` |
| `99d74b92-bb7e-4497-bba2-2116312517aa` | `phase3-compliance-e3fc55c4` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 07:10:56.255489+00:00` |
| `e242d4f9-f440-417d-8759-2661d91c7f3f` | `phase3-1792a4fb-9e2b-4fdd-a297-2e77591ad5c0` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 09:57:07.111186+00:00` |
| `02672167-034e-4a63-80df-c618beb38349` | `phase3-d97ec9a5-bc39-4489-a3da-69e88f52b61f` | `CREATED` | `None` | `None` | `2026-10-26 11:20:11.885540+00:00` |
| `53f37471-aff3-4aab-8fd1-a74c92f20d33` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-27 06:06:41.088923+00:00` |
| `66e997b0-5e07-4d87-ab33-f50988fbc8fa` | `adversarial-5d1000b2` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 12:31:28.717477+00:00` |
| `e6c2e2c7-45ba-4a14-a053-abbff5bd1d0c` | `supervisor-e2e-a8fba329` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:52:15.457070+00:00` |
| `aa4ea032-b832-411a-9a25-d068e324f762` | `phase3-compliance-05d392bd` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 06:51:06.361611+00:00` |
| `ec38e4e5-e49c-4ca8-93af-37d6e68649db` | `supervisor-e2e-e2a0e195` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 08:51:41.819008+00:00` |
| `f08e0d8c-f1e0-411a-b631-7a26fe6f292c` | `neg-empty-3e8200` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:29:53.616646+00:00` |
| `9b3d9dc4-c342-4295-ab44-95261a3b6a05` | `supervisor-e2e-3d4f5d50` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:53:46.413837+00:00` |
| `4bfbdba2-0c23-477f-99ca-6f272047a588` | `phase3-7478e185-18e4-4ef2-a813-871b63043d79` | `CREATED` | `None` | `None` | `2026-10-26 11:21:06.143006+00:00` |
| `7506b42b-a4eb-4c09-856c-dcd8af23479f` | `adversarial-f4a49390` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 08:53:00.097584+00:00` |
| `183226af-271d-4b0a-b2b3-a37c03b5ba1b` | `phase3-9022c733-4bea-4837-a5ea-344ca5f4d028` | `CREATED` | `None` | `None` | `2026-10-26 06:11:38.770677+00:00` |
| `2b74d55d-364c-435f-8dbb-29c2c2bdf277` | `phase3-compliance-1a1cab89` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 08:51:52.795750+00:00` |
| `3f8a0ccf-1fb9-4fc8-bf41-e63bef09c28b` | `phase3-a597cc4e-5e7d-4177-927c-8296acbdc1a9` | `CREATED` | `None` | `None` | `2026-10-26 11:23:28.966657+00:00` |
| `84a9b53c-8ece-4d72-ba0e-be02d603bfc5` | `supervisor-e2e-81d543d6` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 08:51:52.712483+00:00` |
| `d82fbd75-73c6-40b7-ae69-aa95881b562a` | `supervisor-e2e-3006d62f` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 08:52:01.740003+00:00` |
| `ef13281b-7f19-4235-9ca2-3d941fa45dde` | `phase3-d1042add-a2d1-4880-b729-2bb95f85ee1a` | `CREATED` | `None` | `None` | `2026-10-26 11:24:39.865398+00:00` |
| `edd8731b-64e4-4f22-93de-cdb3bcf42c1c` | `test-6912a50e-21c9-49e9-991e-b3f49118a53f` | `CREATED` | `None` | `None` | `2026-10-26 11:25:43.619803+00:00` |
| `4d119e76-6613-4a51-87e3-acd6f10643ef` | `phase3-0105e2bb-3f1f-452e-be0a-2258bf9b6673` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 09:25:12.332171+00:00` |
| `dd52d6b2-b996-44c0-9822-9a8c4dcc1cb9` | `phase3-391aa487-89a9-42a7-b937-6ed2d70c1bf0` | `CREATED` | `None` | `None` | `2026-10-26 11:55:37.146552+00:00` |
| `dcffbfd6-8653-4017-89f4-0432ca6010ea` | `phase3-eaa4be9c-bce5-42b1-b768-2ff2900c78ab` | `CREATED` | `None` | `None` | `2026-10-26 11:27:01.940660+00:00` |
| `0e42cfc4-8570-4a8a-a5ce-0db2a0e61eee` | `phase3-8ed23993-ec19-4faa-bb2f-c1fd989861eb` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 07:10:22.719414+00:00` |
| `bf69ed19-1cd6-47ee-b51f-df9b6c545dd0` | `phase3-3c4efa56-2758-49e5-ba8a-3d0f8fc220f8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 08:35:38.544712+00:00` |
| `533cfe9d-1f2f-42b7-86e4-c931042c28e6` | `test-p4-p5-64d866` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:55:27.382126+00:00` |
| `146a3c9a-ae12-4ded-b023-29e71ba60c5a` | `neg-untested-97c9e2` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:43:26.475110+00:00` |
| `8c9f530c-5540-488e-9a47-b55b72c426fb` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 08:02:19.727836+00:00` |
| `0284e2e6-ca3b-4966-9b87-f2c15679af42` | `adversarial-fba94ced` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:22:05.531431+00:00` |
| `57a2ada2-49a2-4693-bccb-ef3d35da7226` | `phase3-209a32e3-c58b-480b-b0c9-dc2e4631ce22` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:27:17.288664+00:00` |
| `6c4ded4d-b23a-404d-9c8b-f22ed05084bc` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-27 10:31:14.627665+00:00` |
| `521ba9d9-a694-4232-8d3d-1533d3c5d441` | `phase3-d51f6293-0e80-4fe0-b726-91e0ef605311` | `CREATED` | `None` | `None` | `2026-10-26 08:35:40.763265+00:00` |
| `4f2ae50d-8be9-4e30-a2ea-e071e69f48c6` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:05.833268+00:00` |
| `58eb1922-13a5-4c34-bb84-999bfe0b94d8` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:06.083193+00:00` |
| `c4d9d039-0bd5-4892-92ec-d62f3250b0c9` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-27 10:31:15.514648+00:00` |
| `752eb53d-46fa-4a73-96a4-6002d5af3fae` | `phase3-2ee47076-621a-418c-b5a1-406840a5311a` | `CREATED` | `None` | `None` | `2026-10-26 09:25:14.865146+00:00` |
| `9c08fba7-f01a-410a-8264-9335777bd8fb` | `supervisor-e2e-84a18895` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 06:40:01.333984+00:00` |
| `be087589-258d-4d0d-bf85-d78bc8bbc76e` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.174670+00:00` |
| `a5e508a0-3340-465b-8bbf-0c7d4daef975` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.279577+00:00` |
| `59c920e3-d607-460d-941f-23bd3b444c0c` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-27 10:31:16.324526+00:00` |
| `11e519ea-d3c3-42c7-ade1-d9d54f3e47db` | `phase3-4cbdefa4-b628-4a84-ae51-291744bec0a0` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 06:42:01.175047+00:00` |
| `51ebce52-19b0-406e-8f0f-d358e47fc2a0` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-27 10:31:17.044804+00:00` |
| `3dcbfb90-7662-4945-a092-85c1de4e0a6c` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 07:08:13.786498+00:00` |
| `8928d1ca-b022-496b-872d-a8fc3a9ae0b2` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:04.844034+00:00` |
| `07971b86-4c96-4115-9cae-0d4130fd4995` | `neg-empty-39d101` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:12.175321+00:00` |
| `0f448a72-53e7-4cfe-8eac-86daa520c91d` | `phase3-e049385d-9efb-49a2-be0f-62266e466439` | `CREATED` | `None` | `None` | `2026-10-26 06:42:03.474448+00:00` |
| `d53bea14-dde7-4b64-a73d-b249b866f2db` | `phase3-compliance-87fcfa0c` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 08:46:09.400632+00:00` |
| `c10284a2-3af2-4468-8543-86200126c847` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 12:47:28.290407+00:00` |
| `cdb92b4c-8653-48eb-bf95-92bba3a9b4eb` | `Leasing Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:04.945173+00:00` |
| `741f4a42-1cfa-4818-9e72-ff1d2b1a6ff2` | `Invalidation Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:05.064746+00:00` |
| `721cfe92-5b36-475a-8eda-8dcdccd739b4` | `phase3-95cf1470-fe89-44e0-85ca-9adbd524711e` | `CREATED` | `None` | `None` | `2026-10-26 11:27:19.933258+00:00` |
| `357af230-a1f7-45b0-9838-5ee0013634e4` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 11:07:44.062757+00:00` |
| `46ec4001-67af-4a8b-8685-80615ccf22f8` | `supervisor-e2e-8d3de06b` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 08:51:07.228928+00:00` |
| `6be81a0c-9df2-4ec1-a10d-e9215abf909e` | `phase3-15f0f7b7-86f3-4828-a14f-7467fb5880ec` | `CREATED` | `None` | `None` | `2026-10-27 09:57:09.378537+00:00` |
| `9b23a5bb-74da-4c66-97b0-1a51e70f9b34` | `Leasing Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:05.179405+00:00` |
| `5be51e8b-9fe2-4991-a866-940949f5e049` | `phase3-ef7372f9-6e32-4533-ab78-62d7ea7da815` | `AWAITING_GATE_G2` | `supervisor:c72f1f5e3e6b40528decb9134bcd9910` | `2026-10-26 11:06:18.316173+00:00` | `2026-10-26 11:02:39.856588+00:00` |
| `43fd6044-718e-477c-828d-0c187180e0f7` | `supervisor-e2e-20b90019` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 08:51:51.840295+00:00` |
| `1b2815a9-73e1-4ed0-b795-23d1015ca94b` | `supervisor-e2e-75932174` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 06:42:17.620677+00:00` |
| `2c3cf81e-eb19-4b23-b9ac-f12ce7579933` | `phase3-77232f93-21f8-407a-b4c6-cccd5e67c7a3` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 08:51:52.774125+00:00` |
| `5cf9476b-5300-47e8-aa35-387218035632` | `adversarial-6db41596` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:14:41.708749+00:00` |
| `16e451db-c9b7-4d26-b28e-10952cd2ad6a` | `Payment Gateway Modernization` | `CREATED` | `None` | `None` | `2026-10-22 08:50:27.685980+00:00` |
| `fae0de4e-c02a-4226-83b0-ec6635a2e76f` | `supervisor-e2e-ab726943` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 06:58:39.321595+00:00` |
| `6044ee26-b4e1-4377-81d4-1451e5b20120` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:02.807968+00:00` |
| `86b104b5-54a5-4ca9-896a-f5024df5fda6` | `phase3-d46cbc1a-8fa6-4403-a8b4-f5ab5a70ad4c` | `CREATED` | `None` | `None` | `2026-10-26 06:22:58.861505+00:00` |
| `eced1e03-d880-4eea-a5a7-4558625d84ee` | `phase3-b29ff45f-9576-417a-a3a7-e8d0113bd477` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:05:57.646680+00:00` |
| `0558c187-0276-4f97-a5e8-f58c9937ab85` | `phase3-44db12eb-69b5-4cff-aa55-31c67c6d5d37` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:32:56.356951+00:00` |
| `9654d2b6-e4ce-4ad2-bf46-65c68c7782dc` | `phase3-41f35a38-9862-4293-9d74-c0abae22e41f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 06:23:20.200787+00:00` |
| `12feb6e4-4c75-46a9-be52-6c987520e498` | `phase3-1dd74c2b-e161-4ec3-95ab-19da0ba275bd` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:15:00.398235+00:00` |
| `28ab65f5-7a14-4ec2-803c-83a519cda97c` | `supervisor-e2e-ea5a2669` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 12:29:15.822954+00:00` |
| `cc98e7cc-222b-4a96-a121-6c671396fc63` | `test-p4-p5-5e9a5d` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:09:39.267972+00:00` |
| `181e3dd6-cc6e-4ae3-9de3-071669a36310` | `adversarial-45c0a9e8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 06:42:31.633514+00:00` |
| `30cd2b80-bb3b-413c-9089-9fc51722eaad` | `phase3-af683891-402d-4864-b0ba-086ab8c6fde5` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 06:06:50.288456+00:00` |
| `47686e70-e142-4bb5-a6f8-496258204c5f` | `adversarial-ab258c1c` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 09:55:38.266858+00:00` |
| `ac5afbc4-945c-4ac5-91d3-b32a55f5eae6` | `phase3-84faa862-16d4-4505-88ad-f34f3c5c1199` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:15.296038+00:00` |
| `45e9b9f8-89d2-4621-95c3-691ee5082f11` | `phase3-03251554-fc93-4727-be12-287903d3d9a8` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:35:01.335964+00:00` |
| `53ddffe0-b235-4b0a-987d-ea600d009ad2` | `neg-empty-6d49b1` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:45:43.057420+00:00` |
| `f4d2c4b2-99b8-4222-9546-1dca538d4071` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:56:22.025275+00:00` |
| `4a9fa549-03c6-45ff-b6e8-6936bbb1cc9c` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 10:47:08.150611+00:00` |
| `39214511-1367-44f5-8f39-a15c7e0fc932` | `phase3-compliance-69907315` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 12:33:07.453667+00:00` |
| `7d9fdf72-a0b1-4d1d-af71-02772e9f2a31` | `adversarial-9866abf1` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:53:41.633824+00:00` |
| `0cb3a83a-2447-4c06-bd62-f91e708c6ff0` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-27 10:31:30.967524+00:00` |
| `3d65e9eb-81fb-4773-8307-aed1f140166a` | `test-p4-p5-99a49f` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:09:39.545175+00:00` |
| `76877df9-f5c4-43a8-80fe-92190bc9f5a9` | `adversarial-de178791` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:05.324159+00:00` |
| `2709fcfa-4e7b-4192-9762-50cf4cccff74` | `supervisor-e2e-e2ec6d42` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 11:55:54.543378+00:00` |
| `f3794e16-cb1c-4e5a-a3ec-88301b12f81e` | `phase3-compliance-456c25c2` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:35:01.114403+00:00` |
| `a1d33ed1-c840-44bd-8e47-2a22837f59c2` | `neg-untested-873416` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:52:23.387388+00:00` |
| `98518be0-c965-44fc-8921-29500efb0734` | `phase3-92152b78-950a-4bcb-88cc-e7e5cec59ffd` | `CREATED` | `None` | `None` | `2026-10-26 10:06:00.627925+00:00` |
| `06bb4362-d93d-4076-84a0-ce9b31fb3a38` | `phase3-compliance-95cd91a3` | `AWAITING_GATE_G1` | `supervisor:14c4c4cf7e4d4de9a899a149b0d6f742` | `2026-10-26 12:37:08.576577+00:00` | `2026-10-26 12:32:58.578589+00:00` |
| `a751c336-8790-47e5-bf2c-f6ec6c2de287` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-27 10:31:31.574900+00:00` |
| `5f58706a-c31b-4039-9c0f-61b425f4e55c` | `Intake Route Test Job` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:32:57.750304+00:00` |
| `396f9163-40ab-4cab-afe8-0a3126bbe904` | `neg-untested-c0bba1` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 12:33:07.459012+00:00` |
| `314945f6-f754-482a-b55f-447218c36012` | `adversarial-5756901c` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:09:39.522371+00:00` |
| `897ce66d-ad69-432e-aa52-1154bf6b4567` | `adversarial-7d36b3a8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:32:02.447597+00:00` |
| `7b2c74d7-42e7-4d0a-bb0b-edd5d1955935` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.375222+00:00` |
| `c29a402d-49b3-4414-98f2-1982e4526b90` | `Leasing Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.478334+00:00` |
| `3c16e77a-c364-4e9f-9346-6b5d906487d7` | `phase3-be5e9393-9eaf-45fa-8030-a4c4e3bcdf5c` | `CREATED` | `None` | `None` | `2026-10-27 05:53:04.438946+00:00` |
| `96833e51-d628-4bfc-b837-158f1e7c646d` | `phase3-1d468900-6c1c-4a81-b50f-bf83c8ec2e78` | `CREATED` | `None` | `None` | `2026-10-26 06:23:22.355064+00:00` |
| `d8de3e2a-2d8a-4717-87f8-c346d0c6643d` | `supervisor-e2e-5136d992` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:55:54.503523+00:00` |
| `4653c55d-17d9-4a72-a4a1-8f0fa11c900b` | `test-p4-p5-6c8756` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 11:18:10.272135+00:00` |
| `701ea3e0-b7c1-4dc0-a8a0-0dedbeeed8b2` | `phase3-compliance-8b5e470a` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:20:36.264541+00:00` |
| `988bc645-132f-4237-9446-67b43c0970c5` | `phase3-compliance-5ff7d862` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:27:37.723364+00:00` |
| `3665a0c5-82f4-41f9-aedd-cfff6357eaf8` | `adversarial-cca16a34` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:18.915694+00:00` |
| `6b0d8563-a248-4e61-ae86-3925596c0cf9` | `phase3-compliance-f8794885` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:45:43.168517+00:00` |
| `3c2a3bb2-c528-48c8-89f0-1ab60cd156dc` | `supervisor-e2e-b88a9e8b` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 05:39:19.354135+00:00` |
| `100d5ec3-7ac0-48f6-8234-dc59ea37276c` | `adversarial-53da1ccf` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:45:43.487067+00:00` |
| `a1a3ccd8-8c3c-49ed-bdac-08eae6be6708` | `neg-untested-93766d` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 12:15:34.635036+00:00` |
| `89bea42e-cd39-48a4-aa11-d3ab3b25134a` | `phase3-58834179-2e12-4243-938f-2b77d467c895` | `CREATED` | `None` | `None` | `2026-10-27 06:06:52.855337+00:00` |
| `73096b42-c65c-444e-8002-faf649eed779` | `phase3-f0aa9188-9b7b-4d15-9ba3-0f4938bcac85` | `CREATED` | `None` | `None` | `2026-10-26 11:15:03.737914+00:00` |
| `503b54f8-ee54-425a-9b27-762cc93e6c25` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:02.907046+00:00` |
| `20e9c17e-d19f-49a9-9b6f-dc289d3ef3c2` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 06:24:03.009308+00:00` |
| `3f1ebc75-36ba-44ac-a506-89fec740b871` | `supervisor-e2e-81fbd099` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:41:31.959397+00:00` |
| `044e288a-03ca-407b-8c15-230245ecba7d` | `test-p4-p5-c1c882` | `AWAITING_GATE_G2` | `supervisor:eb42777551cb40a69b56e94f9ebb7259` | `2026-10-26 10:51:11.864054+00:00` | `2026-10-26 10:47:02.187376+00:00` |
| `5dd34f08-0ab1-41d0-a65b-92182a77dcc7` | `phase3-464b385c-1e2e-46cf-afe1-4b1838a21303` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:56:50.437821+00:00` |
| `40708f6d-6e62-4dcd-b598-349011842f24` | `phase3-compliance-b48cdac2` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:18:10.286550+00:00` |
| `7832414c-2d35-4f0d-ad03-012e3c0b1537` | `neg-empty-47bcec` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:51:30.398809+00:00` |
| `945e6f71-909c-4e6e-b502-ca3d0bf39cb6` | `neg-untested-273de9` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 12:17:19.364953+00:00` |
| `6a272b43-32be-4a17-905d-46949d731e95` | `phase3-597f5883-3a26-477c-8285-e284bf708a02` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:17.275868+00:00` |
| `1d1323b0-837c-4b85-94f1-85c6377be4a1` | `neg-empty-ed17b9` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 12:29:15.859734+00:00` |
| `ad7454f7-b71f-4c49-96c5-53c3ffeb8e80` | `neg-untested-6d818e` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:30.182033+00:00` |
| `fa35fdea-86da-443b-9d06-959a3c445059` | `supervisor-e2e-435dd451` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 10:51:30.487468+00:00` |
| `73e3e37c-801a-4c56-bf11-6c5a100016fd` | `phase3-2cdcb3e1-3b0c-44b4-9cc1-bc15ee4477b2` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 09:16:23.475502+00:00` |
| `b9134283-7819-4684-9b65-a3c19420fdb9` | `neg-empty-e95756` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:17.514090+00:00` |
| `743ec3c9-9a48-4a1d-b63e-559c47b906ea` | `neg-untested-bc6478` | `AWAITING_GATE_G2` | `supervisor:7b667d79968047588c8f8725b953ec28` | `2026-10-26 11:17:24.845289+00:00` | `2026-10-26 11:13:46.259127+00:00` |
| `99b34778-b6d1-42e7-89be-404f1cb79742` | `neg-untested-ae7c56` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:17.500533+00:00` |
| `87a21e2d-ecbd-45d5-b994-1f8e6de3a492` | `neg-untested-357cf7` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:11:19.367357+00:00` |
| `689d741b-4509-4fe5-b892-a9651f999d20` | `supervisor-e2e-6805ee7d` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 09:32:51.461080+00:00` |
| `f1c83a3e-2434-46da-95be-c2b2b62926e1` | `supervisor-e2e-e1df16a3` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 12:29:15.898824+00:00` |
| `79e3a212-3687-42ad-a9e3-8dfa1ef33546` | `Invalidation Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:05.310764+00:00` |
| `a74a4352-d627-4283-be90-660f61998b06` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:05.446716+00:00` |
| `5fd0982b-58cb-4c68-a995-ce9b135df768` | `adversarial-eebf532a` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:51:19.409297+00:00` |
| `c553fdd9-6473-4a4e-a641-38e9bf26f807` | `supervisor-e2e-65d823fd` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:04:52.272543+00:00` |
| `b6431b34-7e5f-466f-bb98-dde29bd14d96` | `phase3-3935d9d1-df83-418a-8e08-32cab813f473` | `CREATED` | `None` | `None` | `2026-10-26 10:06:54.190124+00:00` |
| `986914db-6b75-46fa-b83f-175c35996dbc` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 11:07:16.667445+00:00` |
| `324ce983-2817-4a3f-b5f3-f0aee7252bae` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 11:07:17.681870+00:00` |
| `97fe5a01-a888-4e83-90f9-cf62a3fbeb3f` | `test-p4-p5-32ee63` | `AWAITING_GATE_G2` | `supervisor:68ca0e1d71a045059d5f99a8aa197365` | `2026-10-26 10:53:03.872630+00:00` | `2026-10-26 10:48:54.276684+00:00` |
| `30992e77-144f-4824-919c-e098f0e07a3e` | `supervisor-e2e-ae773ff6` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:11:54.212348+00:00` |
| `ee085126-1c20-4574-85e9-1984280b3884` | `supervisor-e2e-82e9b9bd` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:03:48.749397+00:00` |
| `67285f4c-59aa-4461-a0aa-3d3d9cc8d449` | `phase3-compliance-47af76db` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:15:10.445237+00:00` |
| `c34f86d5-87f7-4fc1-bddc-b450fd04feec` | `neg-untested-17e499` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:19.866204+00:00` |
| `a77d249d-d1fc-4735-a6fb-26e4346fb0ea` | `phase3-7dde0fbd-2770-47f1-b716-03bafc88d82d` | `CREATED` | `None` | `None` | `2026-10-26 11:56:52.872039+00:00` |
| `13d2b451-1ef9-4694-85dd-5c9c186054c4` | `phase3-8d6a4c76-0445-4289-a8ed-8a88ea65a997` | `CREATED` | `None` | `None` | `2026-10-26 10:10:14.330942+00:00` |
| `26d0eb7c-c46a-493c-8d90-cee3d5cf0f64` | `supervisor-e2e-e716709b` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:03:50.490859+00:00` |
| `dd37621a-1ab4-4e49-9296-4a602f7b778a` | `neg-untested-cffaf1` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:20.001614+00:00` |
| `f24e2ecf-ec03-4554-96c8-2866bd971917` | `test-p4-p5-e818b8` | `AWAITING_GATE_G3` | `supervisor:85217dca9fb641dd9a64752a0db4fad7` | `2026-10-26 12:34:05.684698+00:00` | `2026-10-26 12:29:59.269812+00:00` |
| `8a728c98-5738-4ae8-9df0-2ec0892223c0` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:05.583860+00:00` |
| `c50d49e6-989c-407e-8987-981250fe2e43` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:05.714045+00:00` |
| `52955cf7-cd2c-40da-8823-5280b8128fef` | `phase3-1b15fd0f-ac9d-47a5-977b-058d68f79a20` | `CREATED` | `None` | `None` | `2026-10-26 09:16:25.557243+00:00` |
| `9498bc22-b91d-4d00-a889-60611c4990ab` | `adversarial-e9233d3f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 06:24:45.227986+00:00` |
| `d895ea83-6f11-49d2-9cf6-e47b59fefb5a` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-27 09:04:33.546860+00:00` |
| `0687f172-c0e3-49c7-9331-fe7c1df8aed7` | `adversarial-e9ac5c4f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:54:12.364657+00:00` |
| `8e32a1e3-d238-432a-b615-987b2abb6dc9` | `supervisor-e2e-1e22b18f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 12:08:23.341098+00:00` |
| `0ee6189d-a0df-4c78-9a30-d2840b4267f4` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 12:16:32.013530+00:00` |
| `39e9f915-2045-488f-b076-6316de4d80ab` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:03.110734+00:00` |
| `7c58df2d-48f7-4b1d-8c77-7b84a2ec558f` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:03.221753+00:00` |
| `9deba533-c384-471e-b0b6-4ca6f861cef0` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 06:24:03.506332+00:00` |
| `32d65838-13db-436b-989a-9db9efad3147` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:04.080106+00:00` |
| `e8e2532d-d6c0-4591-8677-31fac72a9daf` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-27 09:04:34.617227+00:00` |
| `3d69bc10-60bf-48d6-b4bd-f87555e331dd` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:04.310772+00:00` |
| `e1a66258-388a-4f06-8703-31365673cbc8` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 06:24:04.410622+00:00` |
| `21f491a0-c1a0-431b-bf5f-5e9a68dd12dc` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:04.510680+00:00` |
| `855bff01-3a43-404f-b46c-f4f74c3542c8` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:02.071258+00:00` |
| `08cc2b3e-bca2-452f-9be7-b96e983cddc7` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 06:24:02.269052+00:00` |
| `591d218b-7124-40c9-a2cb-0a0df008cd46` | `phase3-00eb53bc-6196-4989-93cc-e3fb93bf3dab` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:11:39.659027+00:00` |
| `c9faaf63-52dc-473f-b1dc-a9f836a5f180` | `Lineage Test Job` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 08:01:29.278996+00:00` |
| `7eec917a-7f91-48ce-ae00-cdcd89b67f01` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 12:05:57.787946+00:00` |
| `ff5417cb-d1fc-4e3f-9c02-81672bcdba19` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 06:24:06.571540+00:00` |
| `010e98af-d8d9-4dbe-821d-23da71146a79` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:06.781538+00:00` |
| `6c6443c1-878d-45f7-b744-59e84b1adcb3` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:06.925888+00:00` |
| `19773c91-1c78-4bb3-b0a6-61f604fb5468` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:07.024411+00:00` |
| `b12fdf00-3ecc-4cc7-b157-81c6c33cd67e` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:07.277226+00:00` |
| `2a032556-a41e-4fb5-a205-a51cdeabb5c3` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:07.376785+00:00` |
| `b7d06cc7-cb10-44da-9e0b-02551c8e5776` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:07.764415+00:00` |
| `8ceacf0e-6e4e-49c5-9a92-6ecd95f196d5` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:07.867460+00:00` |
| `4bd4dc8a-0ae1-4fd9-9409-5ae56030f145` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 06:24:07.977241+00:00` |
| `0904c04f-bf8f-4857-9e09-95064c77675b` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:08.077243+00:00` |
| `cb167859-2635-4984-9302-bda023b44c19` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:04.618550+00:00` |
| `aee8b845-1848-470e-a535-529c4c755dc0` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:08.310564+00:00` |
| `5bf5c555-adf5-4672-b822-d9685e5c2bad` | `Leasing Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:08.546813+00:00` |
| `bfe75fe4-3ab3-4f9f-94c0-eb9a2e3b7f42` | `Invalidation Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:08.648164+00:00` |
| `cf7a573a-b451-4d51-bb8d-39a484e78ecd` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:08.877276+00:00` |
| `9a0e901d-1fba-459c-a80b-2e9c71b47fa9` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:08.984576+00:00` |
| `44dc3108-8be8-4d83-837d-ca2eef1617a5` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:09.085526+00:00` |
| `d01b00a9-225c-40da-88e3-413ab970e9ce` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:09.186253+00:00` |
| `fea5cbea-0736-4600-a9aa-f49396ed76f7` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:09.293396+00:00` |
| `65f48420-bc6e-416b-9cb8-71a8fee27eb9` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:09.392527+00:00` |
| `ac18fd2c-a138-4282-90aa-95704e1668b9` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:09.646161+00:00` |
| `ad4955da-157d-4e77-b273-e5e339d9a365` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:09.743772+00:00` |
| `525c721e-27f1-4596-be16-74f7ba71d00b` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:09.851127+00:00` |
| `1e58c9dd-0215-42c2-b0d5-6149dd43a883` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:09.946867+00:00` |
| `bcaad41b-6522-4f48-948c-6ebd8e18137b` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:10.070413+00:00` |
| `8f0d51eb-6c38-4c98-9503-7488f045ba07` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:10.168261+00:00` |
| `e815db42-c378-43af-944f-1ab4c9361446` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:10.410460+00:00` |
| `5222ab2c-7643-4c86-8a4e-3051a355c290` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:10.518297+00:00` |
| `70cc05e2-7408-4ad6-a88a-0afd73569f05` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:10.619535+00:00` |
| `3a4fb41d-bbc5-4b96-8c72-cff91086bb20` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:10.727943+00:00` |
| `7616bab6-ee34-44c7-8f0b-73c0d33c9773` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:10.824520+00:00` |
| `562b5ac0-adca-46f2-882a-7998a48654d3` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.072373+00:00` |
| `5b0d2b5a-8400-4478-8d3f-74e1ab1e8339` | `Invalidation Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.576433+00:00` |
| `5086a3d2-9266-416d-8cbf-d09e7bfc45cc` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.679910+00:00` |
| `66d9fee8-839a-45bb-9732-cd6fae5ef663` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.780421+00:00` |
| `da679042-b4e8-481d-ae5c-a481286be5b8` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.892034+00:00` |
| `9e576dde-54a8-4adc-aac0-dab8b63980c2` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:11.997592+00:00` |
| `108ecca2-2f20-48f3-8c94-da78096ea3a6` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:12.099467+00:00` |
| `be415851-2a08-44d6-ac48-ce57696ae680` | `Leasing Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:12.209117+00:00` |
| `36696d13-2bcc-4272-8da3-b3734c99da53` | `Invalidation Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:12.325344+00:00` |
| `6a52b55f-60a8-4891-a5fc-7f17b9e77dab` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:12.431233+00:00` |
| `2cfce345-4078-44cf-a6f6-bf9c09e1fa94` | `phase3-9d8db2a1-3b2b-458a-9f89-7fcb6e451cf3` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 06:25:22.474193+00:00` |
| `d1c8246e-2b69-4660-bc5c-9f6bde338b65` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 11:07:44.709132+00:00` |
| `d4905855-edd5-4d15-b536-b09660e8ea3f` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 07:22:34.640690+00:00` |
| `baf51a32-1a09-4a69-a67f-46841dcf10cc` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 06:26:02.709367+00:00` |
| `d60e1f0a-aede-403f-bebd-2fc351b43428` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:12.663872+00:00` |
| `3eca950c-cd55-4088-b906-bc1b99d1fe94` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:12.777029+00:00` |
| `c4d8e415-8432-48fb-a7cf-723b476e32c9` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:12.895605+00:00` |
| `96f8dfee-3feb-4425-81dc-af14f2384c91` | `Payment Gateway Modernization` | `CREATED` | `None` | `None` | `2026-10-22 06:24:13.004576+00:00` |
| `9eee5a7f-bcd9-49ea-bbdb-ea90cc32e1a6` | `Payment Gateway Modernization` | `CREATED` | `None` | `None` | `2026-10-22 06:24:13.114174+00:00` |
| `559259a0-7de9-4f04-8a97-bd398d5f5fc1` | `E2E-Job-c7eeb7` | `CREATED` | `None` | `None` | `2026-10-22 06:24:13.226572+00:00` |
| `08f73ba2-4c15-4a63-98e4-a818a8f73d2e` | `Leasing Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:13.444172+00:00` |
| `c670142a-aa65-4c90-a860-3127f4ec61aa` | `Invalidation Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:13.565103+00:00` |
| `5445721d-ee19-4cf6-bf53-594649797121` | `Job 13` | `CREATED` | `None` | `None` | `2026-10-22 06:24:13.673633+00:00` |
| `7f112162-0360-4123-a5f5-e0c3c160c568` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:13.916704+00:00` |
| `c568b702-1ca0-4929-a9da-eff546a1984d` | `Job 26` | `CREATED` | `None` | `None` | `2026-10-22 06:24:14.021038+00:00` |
| `756722cf-4462-4e93-a1e7-7b13a2b99f8f` | `Job 33` | `CREATED` | `None` | `None` | `2026-10-22 06:24:14.128225+00:00` |
| `30c3014a-fed3-405c-a334-8fa27996b9b0` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:14.697515+00:00` |
| `d6703b37-7ab6-4129-a069-4ae9b6101a8a` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:14.803409+00:00` |
| `a506e79c-845d-426e-b8e4-6dd186e2c69d` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 06:24:14.900365+00:00` |
| `5925fcd1-bca8-4832-9231-ba50ecd4acfa` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:15.005405+00:00` |
| `191c7909-01d7-49b2-8115-b7798bdd1b56` | `Job 17` | `CREATED` | `None` | `None` | `2026-10-22 06:24:12.543689+00:00` |
| `f0f302ce-ea4f-4380-b8b8-fb63ec679cda` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 12:48:04.596096+00:00` |
| `5abbc5e7-ff87-495a-8ea8-a01851228136` | `phase3-199f93a5-bb3a-4064-a33f-ed28d9cd85c2` | `CREATED` | `None` | `None` | `2026-10-23 08:13:38.349335+00:00` |
| `5f50389f-def1-479b-a0da-21b70bc5765c` | `phase3-928d1b00-03ba-48ef-acc4-c1ee4ca1894f` | `CREATED` | `None` | `None` | `2026-10-23 06:28:26.948862+00:00` |
| `ba39590d-f84c-48bd-ba84-0611f532ebb5` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:16.765753+00:00` |
| `d86816e3-4680-40cc-9f9a-b9295d41c315` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:16.860115+00:00` |
| `916d5afc-7530-4114-b790-3a77b9337b1e` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 06:24:16.116193+00:00` |
| `e458d1d9-60a2-40c7-9c7c-818e0b47f67f` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 06:24:16.976829+00:00` |
| `ab0b603c-8e95-4ea7-b714-ba16fadb8584` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:17.085227+00:00` |
| `22fb403b-3acb-4836-aef4-804cf9cc01dd` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:17.194388+00:00` |
| `519863a6-8b60-4f0f-9f4a-bd4af5fb20fe` | `Payment Gateway Modernization` | `CREATED` | `None` | `None` | `2026-10-22 06:24:17.297393+00:00` |
| `063ca16d-83d0-4e6c-8e6e-71fcf5e6edf7` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:17.393041+00:00` |
| `836643ce-62ac-4e51-9b9b-1e1768d426f0` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:26:27.793179+00:00` |
| `87c75a69-d2ad-4143-8962-114dbc2718c8` | `phase3-22517a99-1961-4059-89da-2f11fd7ac1b9` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 06:26:28.931053+00:00` |
| `fec2a160-b378-4c5a-909e-32ee5f69dfad` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:15.648908+00:00` |
| `6d49ac7c-cb42-443c-85d6-74b83bd42547` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:15.757447+00:00` |
| `6852be77-2b95-4a56-95d5-f0c0dc4d0af5` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:15.855414+00:00` |
| `cc30a393-6768-4f5b-8cd4-712412ddbea8` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 06:26:03.697104+00:00` |
| `884f2d37-dcb9-4197-ac4c-f7b427fbbafe` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 12:48:20.816379+00:00` |
| `afe4f042-9add-4fe6-92f7-1d92d18b32d9` | `phase3-7e8c850a-9da7-4acd-9273-cc2f50887470` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 06:24:17.603281+00:00` |
| `a6b1840b-e9b0-4a38-8b6e-ee22d0780f84` | `supervisor-e2e-a0a59e76` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:54:55.986515+00:00` |
| `81aeac4d-a7d5-4478-a2f4-c1b9043eeaca` | `phase3-6c4de1ed-38ab-47f4-8d42-53252922f227` | `CREATED` | `None` | `None` | `2026-10-22 06:24:18.515335+00:00` |
| `5e11c31d-d47c-43ae-a609-de27dedb18c5` | `Gate Decision Integration Service` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 06:38:24.949845+00:00` |
| `34a2fe1a-6a10-4bbc-b4d6-e92dbe23486d` | `phase3-cf169a04-f436-45bc-b337-8548e60461b3` | `CREATED` | `None` | `None` | `2026-10-22 06:24:18.943375+00:00` |
| `87c14f60-1064-4d21-9e97-9e23cbdebb07` | `phase3-ac157a14-9fbc-4f01-b714-55e9caa2be87` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:05:56.754458+00:00` |
| `298f10aa-bac2-4f7a-8e0e-90a7f04f0aab` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 12:06:15.702726+00:00` |
| `b13495b8-4f25-458a-a2f7-33cf6a86c5cd` | `phase3-033e5768-addb-49fc-965f-54ab5a1c75fa` | `CREATED` | `None` | `None` | `2026-10-22 06:24:20.299159+00:00` |
| `121345b5-b788-42dc-a8f7-4809a8ee8a25` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 06:24:20.403538+00:00` |
| `03d3dbb5-8ecb-41a0-b336-1d00da4f9836` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 06:26:04.561255+00:00` |
| `f74a18fd-96c3-41cd-937f-ab57cbe37d1b` | `phase3-5657c8e2-cace-4ba7-801b-90ed66283dd4` | `CREATED` | `None` | `None` | `2026-10-28 11:33:00.899054+00:00` |
| `a3ad5dfa-f2ea-4990-a3b8-30bddba6a5f2` | `phase3-27c1faf8-d019-499c-a185-5b13c52359e8` | `CREATED` | `None` | `None` | `2026-10-22 06:24:21.076680+00:00` |
| `dcb04a6f-4fbe-4fef-b716-2b1e099763c7` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:22.449965+00:00` |
| `17aaa66d-7ed5-49cd-9c58-96677128665a` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:21.186194+00:00` |
| `f63fbc47-0847-40ab-8b74-801c911a501f` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 12:06:16.667927+00:00` |
| `de2ee4c2-cd76-40cb-80e8-72d1c2bb81e6` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 12:05:31.876539+00:00` |
| `7ae410d4-591d-4b25-bd24-89b96481e52c` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:21.747822+00:00` |
| `3c672565-b268-465f-a161-0d23bdc1c3d6` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 06:24:21.978306+00:00` |
| `950e5438-0117-4f10-9510-6618b4bf8a3f` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:22.100538+00:00` |
| `f0c9a4f7-d2fd-4eac-94e7-873f2397d0da` | `phase3-e76710b3-0269-4eb0-932a-67a47f6a4289` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 06:24:22.755743+00:00` |
| `df640879-ac58-475e-965a-6ec3e58218e1` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:23.167689+00:00` |
| `12377930-4b69-44a9-ae93-7bc810e7434e` | `phase3-7c5406f2-8ee2-4e91-ade7-08746aa89a6c` | `CREATED` | `None` | `None` | `2026-10-22 09:37:19.705448+00:00` |
| `d4558f4e-be97-48a8-8f78-62fc45baba38` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 06:26:06.021406+00:00` |
| `51377ff3-1647-4ad2-b121-04fe0fd7f77f` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 06:26:28.443457+00:00` |
| `b3d1ab51-eeee-48cd-bcda-7669b4d3ac57` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:22.207531+00:00` |
| `59993bf7-4432-45ab-9de2-170c6f1490ea` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 12:05:33.194468+00:00` |
| `bf68eab2-27ed-48c2-b4dd-55c851378e2f` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 12:48:21.707352+00:00` |
| `2a1dc57f-5e47-4bdc-9f4a-44e9e723cddf` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:23.274748+00:00` |
| `ea421165-e8f3-451d-81ca-02bfe578594c` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:23.367560+00:00` |
| `d45dc3f4-e2d2-4622-a654-e871e8580040` | `Job 34` | `CREATED` | `None` | `None` | `2026-10-22 06:24:23.612654+00:00` |
| `595b7b38-f256-400f-a807-4940991645fb` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 06:24:23.726063+00:00` |
| `f43362ee-b4db-471e-b23f-1cab4a120267` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:23.937249+00:00` |
| `197a677c-2f6b-4643-ab23-17fc01660188` | `phase3-119881fa-843d-435b-9be6-b0c04ebf1a3d` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 09:37:17.717600+00:00` |
| `78bb850a-3997-48ce-a7ed-e2c98e4fae12` | `Payment Gateway Modernization` | `CREATED` | `None` | `None` | `2026-10-22 09:00:57.929396+00:00` |
| `843e8151-3e2d-49e4-bf7f-536ae8228af3` | `supervisor-e2e-76aeab7f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:54:56.102982+00:00` |
| `b0428ad9-6625-4e5b-82a3-9e4983d2ce83` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:23.833528+00:00` |
| `d471e0ac-6664-4d86-870a-06d3fe970740` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 06:39:11.413021+00:00` |
| `82f643a2-1378-4890-bfd3-d12915149bda` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:24.143102+00:00` |
| `c75559b3-a058-4a6d-894a-c8fb93fb2793` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:24:08.197732+00:00` |
| `eb46e6e3-a508-4f59-b0f4-81e130bacec9` | `phase3-dc67df0c-60e1-43af-a7c3-3cecb53257e2` | `CREATED` | `None` | `None` | `2026-10-22 06:24:24.580654+00:00` |
| `45133bca-58eb-42d4-8e86-5c61286adc77` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 07:42:13.601509+00:00` |
| `3643e2e6-5c5c-400c-b869-c4334a90a8bd` | `phase3-fcf801b4-dd37-46d7-a8d7-96badf6a224f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 06:24:24.693667+00:00` |
| `ae984472-d931-4e21-8400-65f6be205b0f` | `phase3-31013d05-0bfa-42e8-a14d-7b742560fb5a` | `CREATED` | `None` | `None` | `2026-10-23 09:10:27.056375+00:00` |
| `b3613e9d-6b1e-40f0-887c-9ae518b014df` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 06:38:27.748768+00:00` |
| `f9cb276d-0895-400a-ac9b-978e8dbb3aa7` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 06:25:55.667353+00:00` |
| `73245b5e-5587-41de-b393-1f9c35a7dee0` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 12:05:34.291871+00:00` |
| `0adfe16e-3cf3-4e3a-a62e-6ecc22ba6793` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 06:26:17.776364+00:00` |
| `50da5368-a608-40b7-82d3-a561e7a893a0` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 07:22:53.236865+00:00` |
| `fc4e9a8d-c1b7-4def-9648-e0f8821b6b94` | `phase3-bd5bd1da-43a8-4680-9e2e-91db484734ea` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 09:05:57.525632+00:00` |
| `32ae155c-f1aa-40fc-96f0-331841a40a15` | `phase3-42746132-5474-4665-84be-9192c04956e2` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 11:07:45.196160+00:00` |
| `e80ee9e8-c0e8-40d1-8c30-5c2ab4b11784` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 12:05:19.786621+00:00` |
| `bb2915fd-4b9a-4be8-8015-55b8baeb799c` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 12:05:36.532971+00:00` |
| `74993690-38d7-4b8f-8cf4-ec7043522ee7` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 09:32:20.973832+00:00` |
| `de44855b-84db-4fc5-92cb-94e06b18573b` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 09:32:25.780252+00:00` |
| `bd440490-a24e-4457-a3a9-d5563fdbdc73` | `phase3-50fdb983-29d2-4ce8-a045-3180bbd1ad80` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 10:11:30.072124+00:00` |
| `556b015c-3cc5-4b8f-86af-55f83280441c` | `phase3-1091fced-d433-4bf3-b01b-e8959f565656` | `CREATED` | `None` | `None` | `2026-10-22 10:11:31.806721+00:00` |
| `eacbb947-f4df-4e20-9ab8-add2462be63b` | `phase3-f2661c6b-dcdb-4e13-8461-9ad301094ec6` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:37:33.653189+00:00` |
| `1b91b2f4-e5e2-40f4-857a-4a4c99969136` | `phase3-62a79335-1c85-4d83-b38f-f46a6817d28d` | `CREATED` | `None` | `None` | `2026-10-22 06:26:31.098690+00:00` |
| `ad88425a-7a04-4d95-87c8-d6f1caf2f687` | `phase3-243eb24f-1fe7-43a1-8d88-13b1e99923f6` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:40:43.485858+00:00` |
| `33df90b7-3960-45f0-a605-52e02e8f09dd` | `full-diagram-a9ac170d` | `AWAITING_GATE_G2` | `supervisor:c2a390a17a794e228b32256bcec017f6` | `2026-10-26 11:08:02.148887+00:00` | `2026-10-26 11:03:52.606457+00:00` |
| `84d23bce-bdf3-4ee7-879c-fed737033e60` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 06:39:26.344960+00:00` |
| `08c70b76-1690-4184-ad7a-7ce72d6da00f` | `supervisor-e2e-c5297ea3` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:15:38.915669+00:00` |
| `a10a7296-bb46-417d-89db-ed3078c051b8` | `phase3-89770ea1-bd0c-4281-b32f-7935b378c888` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 06:27:29.407449+00:00` |
| `aa133565-5e1d-4309-9fa0-774bbf8a68f8` | `phase3-9225bac6-b1ac-4e4b-a472-887ee5b8e7bd` | `CREATED` | `None` | `None` | `2026-10-22 06:27:31.111106+00:00` |
| `89d138d2-9c7e-46c0-90fe-5dd487cc98ba` | `phase3-81d263f5-c167-49b0-89f9-bde86919462d` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 06:38:03.766057+00:00` |
| `b3fb6c70-c63b-4775-a12a-3d2e627bb294` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 07:09:28.646043+00:00` |
| `afe63626-30c9-4eb9-b0d9-6ac0610fffdc` | `phase3-257868a1-068b-43d5-b2ff-a16e2cdfa476` | `CREATED` | `None` | `None` | `2026-10-22 06:38:05.221930+00:00` |
| `ed1cc88e-1503-4539-ac1f-c89db4f5f708` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 06:38:22.081782+00:00` |
| `c7469752-a762-4d49-aaed-439df2430746` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 06:38:23.230719+00:00` |
| `4e2340cc-de07-4b81-a080-482032dae17e` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 07:09:36.429025+00:00` |
| `785db893-bfb9-40c0-8e9a-ece98c57543e` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 07:09:37.395510+00:00` |
| `12de067a-1f05-4644-95f2-0eeb2e96af5e` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 07:09:38.661681+00:00` |
| `1e3956cb-e782-4522-97bd-4968cb2cfd3f` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 07:09:40.748198+00:00` |
| `fc05eb2e-7287-4106-a219-1baef333eb35` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 07:10:21.458242+00:00` |
| `966dffa6-1134-40c4-80f1-2f2995973920` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 07:10:22.082918+00:00` |
| `e33633a5-1dc2-469b-b265-b89027ba16ce` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 08:02:19.115773+00:00` |
| `a7e8b98d-f5e2-4e84-9887-6f8b4e65ab99` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 07:10:08.192515+00:00` |
| `23bae241-2698-4ecf-b587-d24cf39a5b8d` | `phase3-7d670478-7327-458d-aee3-b55857939661` | `CREATED` | `None` | `None` | `2026-10-23 06:39:29.648120+00:00` |
| `248a2502-9113-4f6a-aa10-f3bb42bd1580` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 07:42:29.117762+00:00` |
| `e49e8a2d-9b7a-49e8-8ee7-fc61786fa22b` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 07:34:24.849374+00:00` |
| `1a7cc1a3-99b2-49aa-940f-b64c69962822` | `Intake Route Test Job` | `CREATED` | `None` | `None` | `2026-10-22 07:34:25.703904+00:00` |
| `e2a4c973-9379-4a8d-a35c-2830243ee828` | `phase3-bdf90c80-d560-468b-acfd-d8454fe1d763` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:43:17.815287+00:00` |
| `e454a9bc-2b2e-4003-9c64-066e0e0139ce` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 07:34:35.883243+00:00` |
| `f0f9fb09-6a83-4caa-a954-5a98b5a9e21d` | `phase3-ec8cc3c6-a51d-40f9-988d-cfe100b8e35f` | `CREATED` | `None` | `None` | `2026-10-22 07:10:24.577439+00:00` |
| `06a58dcb-0c4f-4584-9ea0-20dad4555b40` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 07:35:11.125387+00:00` |
| `2d7c8cfc-858a-4c89-a6a2-e22fb8e8ab1f` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 07:34:37.096000+00:00` |
| `08632897-80d4-45f5-a898-531f8647ba35` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 07:34:38.244811+00:00` |
| `59208fc4-a8f8-4c18-bdd1-d40bf3a5a020` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 07:34:40.249741+00:00` |
| `1c7ac7f9-4fa0-462e-980d-1fccfdcffb39` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 07:35:11.755874+00:00` |
| `3a61e3fe-b3ef-4063-b9a4-39141987293d` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 07:34:57.528233+00:00` |
| `82aeaa24-2e7f-4c41-87d2-af44876cf20e` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 08:01:35.330642+00:00` |
| `a7c8f1a7-30ad-4c3d-acb6-cdbfa3dcdc02` | `phase3-abb4a200-d90c-46f3-aaad-679971f3827f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 07:35:12.193428+00:00` |
| `d1c1b9fd-c196-4f9d-a487-eed47aa3e7ec` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 07:37:19.758754+00:00` |
| `bad7a157-fde2-4fc7-8999-96a427abf3ff` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 06:38:44.450538+00:00` |
| `40586c4e-d1a7-42d3-a201-01e8576d3093` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 06:39:26.962991+00:00` |
| `5acda818-241f-43d1-a367-d1a60cbd9f40` | `phase3-f61dfdce-7900-45b5-b370-48c4a5fa07da` | `CREATED` | `None` | `None` | `2026-10-23 06:53:00.312559+00:00` |
| `7d08d4e2-1264-4a20-8c3f-c6f570e3afbc` | `phase3-25b648b1-4a0c-49e6-8fbf-15fff86b2f07` | `CREATED` | `None` | `None` | `2026-10-22 07:35:14.985714+00:00` |
| `1e38862a-3d69-490c-8edb-1cb1f92c616c` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 12:05:32.198149+00:00` |
| `ba599d8b-fd3f-4fc5-936c-00b202d571eb` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 08:01:46.190638+00:00` |
| `2fd094c5-226a-4f7c-abe4-00e683ece9eb` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 08:01:47.048754+00:00` |
| `28d0750b-2d9d-4dd0-a3a1-76f34bc0b5fe` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 08:02:05.683759+00:00` |
| `30986af5-d226-4bd5-bf24-49696c68fe26` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 08:01:48.012437+00:00` |
| `c0bf414e-51f1-41d0-bea6-e117b72b641b` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 08:01:49.956704+00:00` |
| `eb766951-e64c-4dc9-a95a-2f55f990817a` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 07:22:54.336980+00:00` |
| `cffad80f-4567-4f15-9366-5bd527ec814d` | `phase3-4df33c2a-dad5-4171-8fda-774fdea3edf5` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 08:02:20.118123+00:00` |
| `28c9e167-f5b9-4e60-abe0-1493e3f98fd7` | `supervisor-e2e-db3cf050` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 06:30:45.198250+00:00` |
| `0b829bfc-a49c-4876-8c3d-a147974fc6ac` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 11:15:57.317448+00:00` |
| `8136666d-1a52-4aa6-adf3-a5ce549c9cfa` | `phase3-19be0969-c019-4b14-8405-45a5a4f4870b` | `CREATED` | `None` | `None` | `2026-10-22 08:02:22.332394+00:00` |
| `2cc872c2-3a89-4753-9de2-215629d6a713` | `phase3-4285b2b9-ce1a-4388-bb8e-6926c9d2c83b` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 09:38:46.325881+00:00` |
| `7d958b61-7219-4109-8dfe-c18759bd20dc` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 08:06:28.055168+00:00` |
| `2e9cb136-9a27-4cc4-a197-7df4acff0bfc` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 06:38:46.384918+00:00` |
| `e61263cf-8352-4f5a-965d-68b13047d466` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 08:06:39.129016+00:00` |
| `9b00138a-b651-468f-89e4-71cc9329b360` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 08:06:40.332586+00:00` |
| `e4ffedf8-9ceb-403d-9be6-b1729e96455d` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 08:06:41.194473+00:00` |
| `a28a7b0d-a50f-4ada-a2a2-28c88116595b` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 08:06:43.196378+00:00` |
| `4e8ec1df-2d73-434c-a137-1c243c26366e` | `phase3-7ef3186c-6be9-43d3-b03d-d3083e4743ed` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 10:26:28.162196+00:00` |
| `fb1750bc-8b15-42ce-bb0d-515f10fed998` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 08:06:59.091938+00:00` |
| `b996548b-c9be-4100-a321-7b916dd4f42f` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 08:07:12.316278+00:00` |
| `464a1cc9-3c0d-47df-8909-9d3caf827f41` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 08:07:13.100477+00:00` |
| `228d9e14-88b5-461e-8281-71d65cb0bda2` | `phase3-95ae9fce-1ddf-498b-8f1a-c9ac4eaee0a6` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 08:07:13.586859+00:00` |
| `15c0667c-462c-4545-a2d3-3dddea120f48` | `supervisor-e2e-bcd064ab` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 06:30:46.318128+00:00` |
| `f5eec10e-00aa-42d1-8fe1-58edc52f084f` | `phase3-9e77be1e-3808-4f55-b1ab-07042cad5df3` | `CREATED` | `None` | `None` | `2026-10-22 08:07:15.257824+00:00` |
| `e6291034-12da-47af-ac63-447665159d11` | `phase3-0c9ca160-5db5-4ea5-b01b-141dd475b51b` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:52:15.948936+00:00` |
| `3fb5ed57-928e-47ca-96cc-5ff8e93cec71` | `phase3-f050055e-909d-458b-8529-343cb370f888` | `CREATED` | `None` | `None` | `2026-10-22 09:38:47.737580+00:00` |
| `f82b551d-eab9-4ef6-b37b-c2f44bcc2616` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 06:38:47.537500+00:00` |
| `8feec49d-165a-4954-a47a-b578e081b00c` | `adversarial-40ca87ce` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 09:50:45.306518+00:00` |
| `6f444d8a-bca0-4c7b-b8c9-ad1177f6d916` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:51:33.212498+00:00` |
| `1aebbfe4-0e7f-4240-90cf-590aae3463bf` | `test-p4-p5-dadc13` | `AWAITING_GATE_G2` | `supervisor:21eb82d8a0714488a4a5bff918c06fd7` | `2026-10-26 10:54:04.398918+00:00` | `2026-10-26 10:49:54.799603+00:00` |
| `aac25db1-882b-4822-bde1-392712e52d8a` | `phase3-ed2783b5-224f-432b-8bc5-30811b96692c` | `CREATED` | `None` | `None` | `2026-10-22 10:26:30.030370+00:00` |
| `0e3fea70-863d-4f42-b220-02de75b1583d` | `phase3-90911fae-c3e4-4e63-9655-5b941f1643bd` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:22:55.143810+00:00` |
| `752a2607-51dc-4099-acff-140d0064661d` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-22 10:44:46.199282+00:00` |
| `fadeff2b-daa1-40a1-b6c1-8c895d5ee644` | `phase3-183aca4c-4115-4b5c-86e8-dc585ff05d3e` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 09:04:40.755569+00:00` |
| `367d0281-789b-4e98-9611-b60c528dd0a3` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 09:55:48.422998+00:00` |
| `e24fafb6-7b5f-4647-8313-add01839051b` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 09:55:58.562030+00:00` |
| `3e0b280a-c433-444a-8ba1-a7746398386f` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 06:38:49.738462+00:00` |
| `c20735fc-46f1-4a09-80b6-2bbe46e9056c` | `phase3-288f9674-b090-4f84-8be9-407ea7ea526f` | `CREATED` | `None` | `None` | `2026-10-26 11:15:40.191468+00:00` |
| `365669c4-49c7-4977-88f6-5ff06e21b171` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-28 11:37:25.557148+00:00` |
| `5c1a8488-534c-434e-8a71-7d52fff80618` | `phase3-5a07f041-c5e9-45f5-a1a6-f0845ebe6529` | `CREATED` | `None` | `None` | `2026-10-23 11:07:47.076764+00:00` |
| `2bc23c57-9611-4680-a8ef-1900d18a6208` | `adversarial-690f0706` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:55:41.354975+00:00` |
| `eafdb212-83f9-45d1-9a55-886d1dee640e` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 10:45:01.354113+00:00` |
| `995f35aa-9419-4143-8579-e2b27b799e18` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 09:51:33.830263+00:00` |
| `a7d4eb12-820c-410b-814a-6ecffdb8179f` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 07:42:30.319768+00:00` |
| `81bfa778-8083-40fc-b44b-b07efe664c32` | `supervisor-e2e-491b69bd` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 06:32:31.214979+00:00` |
| `b769ca42-a7be-4a08-805f-efdc9395b773` | `supervisor-e2e-61a877d6` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:51:48.020904+00:00` |
| `fdacd3c3-290b-4905-9d35-639092520689` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 09:56:00.073203+00:00` |
| `84eb562b-6cab-48de-bc15-4ba5a0779e27` | `phase3-72968b3e-09ad-4326-bb31-acf0860af8dc` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:28:25.466625+00:00` |
| `0820776a-3228-40b9-baa3-16e42d46ae02` | `phase3-36cd813b-85e5-4005-b3fc-032e86763573` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:39:27.661252+00:00` |
| `8d7c70ef-466e-4e48-ad41-4749408f539f` | `phase3-01613aa8-7721-4326-aba2-d6bc801d89f3` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:52:58.572668+00:00` |
| `1fe100c1-85ad-4bf4-bd97-0bf2cba41f08` | `phase3-af3570fc-5854-456d-9d89-e7d9574cc812` | `CREATED` | `None` | `None` | `2026-10-26 10:11:41.631952+00:00` |
| `a3191106-e221-40b3-81f7-1d74109a719d` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 10:44:58.885158+00:00` |
| `c2329490-21ef-40ba-9540-0962e4079a7e` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 10:45:00.168418+00:00` |
| `dae9d8a1-1993-4483-bb2f-8c9661c83d50` | `phase3-bee81be9-29d9-4453-ad47-b25d40e73f8c` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:54:36.260975+00:00` |
| `e05d153d-31c4-4f6f-a5b7-6889816f841f` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 10:45:03.719827+00:00` |
| `1301030f-54da-4058-8220-a466ee770afb` | `phase3-145d7445-b11e-46f8-b4a1-2ece63dc9229` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 09:21:30.873355+00:00` |
| `9c45687c-96b6-4b3b-bb13-190046557b4f` | `supervisor-e2e-1ebf3eee` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:38:27.792117+00:00` |
| `607ccf85-c520-4642-bf84-b42a41d45825` | `phase3-9b726f1e-faa2-4304-91f7-ac65969aa1a4` | `CREATED` | `None` | `None` | `2026-10-22 12:06:19.520949+00:00` |
| `142ef621-2b36-4bdf-8981-5c8f5ad052b1` | `supervisor-e2e-d83402bd` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 06:54:54.065719+00:00` |
| `fd354552-41be-4524-a0db-8c31b9c6a106` | `supervisor-e2e-5ceae2c1` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:58:42.553542+00:00` |
| `bd62c8d2-c007-4a27-ad93-6934017c3f47` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-22 10:45:24.156371+00:00` |
| `08166c64-6ea6-4ad3-acda-c03191ffddcc` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-22 10:45:40.315520+00:00` |
| `537127dd-b7e7-412f-961b-4ed40a5a46de` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-22 10:45:41.076759+00:00` |
| `3e18760f-92fc-4574-99a2-7023490a1325` | `adversarial-481c52de` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:21.192048+00:00` |
| `a8be453c-69bf-4784-acf3-e6b6eab5bf5f` | `phase3-fc7da073-9e95-4ee0-8e4f-b97e95784d8c` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-22 10:45:41.540079+00:00` |
| `042e2012-aecf-42c5-b124-3b48dd46adc6` | `adversarial-bdbba4d8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 09:33:13.773772+00:00` |
| `24d8cd4b-9ebe-43b4-8a84-d9d9545bc766` | `phase3-compliance-30f3cd49` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:47:57.235634+00:00` |
| `198aae1c-d907-4d50-bdb1-305a012ec936` | `phase3-169cc12f-87e9-4cbe-b101-addbd6ac35d7` | `CREATED` | `None` | `None` | `2026-10-22 10:45:43.630132+00:00` |
| `031cb77f-dc36-4356-ac3c-ef31ac94e0b4` | `supervisor-e2e-312da0a5` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:57:21.232892+00:00` |
| `cb702a23-97b4-45d3-9820-48a5c7f20f25` | `adversarial-4918a2aa` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:46:46.156812+00:00` |
| `7e57ff0b-a2d0-44fc-97a3-d43ac3e1866f` | `supervisor-e2e-f0f295f8` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 06:32:57.977877+00:00` |
| `dc39137e-992d-4a34-83b2-05ebd133234f` | `phase3-801bfcb9-5a65-4110-9b3f-a65731df31a1` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:37:29.293816+00:00` |
| `7b6da43c-f47a-4f1a-a91a-5ca716df85c9` | `phase3-2b81fdde-b62c-4e63-830b-3387a2b97dd9` | `CREATED` | `None` | `None` | `2026-10-22 12:48:24.781443+00:00` |
| `8c4b6ca0-38dd-43f8-abe9-ba479c512712` | `adversarial-d7504225` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:35:06.215902+00:00` |
| `06eb13d0-5741-4d5b-a5e1-ebe8db08af4b` | `phase3-bac6f3bc-bb6a-4fd2-a40e-a4532171c761` | `CREATED` | `None` | `None` | `2026-10-23 06:37:35.637385+00:00` |
| `3e7db4f7-d965-42de-803e-ee5f8230912c` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-22 12:47:40.916388+00:00` |
| `83291efc-968f-43c9-810b-6a3508cf2691` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-22 12:47:42.150647+00:00` |
| `a8660262-a13e-4e8e-93eb-ecc323337058` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-22 12:47:43.266942+00:00` |
| `5148bccb-6520-40ff-94bc-39cebad2032e` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-22 12:47:45.582130+00:00` |
| `f616a3fe-e2ff-4ec5-abd1-c931ca924462` | `adversarial-06ab23f3` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 07:37:35.393953+00:00` |
| `66dcfe97-e53d-42ae-9fa1-14aac3b40814` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 08:21:37.023150+00:00` |
| `f20ed692-6b6b-48ae-bb7c-08959504e0ac` | `phase3-29e65951-b51a-45e6-9df6-6b12ea90e5a4` | `CREATED` | `None` | `None` | `2026-10-23 07:40:45.302193+00:00` |
| `646ee204-7185-4dcb-b7e5-4088a84c5f6d` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 11:16:05.870353+00:00` |
| `8d33b77b-0991-4803-bb79-da48ce2fb603` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 12:05:12.136375+00:00` |
| `667ae214-d04e-4a89-b6b7-655145cc7320` | `supervisor-e2e-02791b6c` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 06:59:59.453123+00:00` |
| `8d4d64ce-18ca-47b2-93fa-6a35e458ccb4` | `supervisor-e2e-2ec405b4` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 08:13:35.565445+00:00` |
| `ccd95a4b-f587-42ce-adf5-550fc636bdc5` | `supervisor-e2e-d1d4d4f3` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:05:21.018141+00:00` |
| `571fafba-d2d7-4f07-b408-093e2433a4bc` | `phase3-616635d1-83ec-400f-a729-f542d2dcf3b9` | `CREATED` | `None` | `None` | `2026-10-23 10:47:40.776598+00:00` |
| `973eaa32-c764-4767-b08f-1a207d5515b9` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 11:16:07.055890+00:00` |
| `5ba0e51e-7768-4bbc-bdf7-380879eee01a` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 08:21:15.276016+00:00` |
| `313ff6eb-be78-4ede-b5ac-a1c9bb8141dc` | `supervisor-e2e-c6b59d36` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:06:07.014131+00:00` |
| `a880faa7-b92a-4383-9d8b-5bb08ea458ea` | `Gate Decision Integration Service` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 07:07:53.033359+00:00` |
| `0ee4135d-01f6-44a5-bf08-cfcb1368615c` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 07:07:56.182030+00:00` |
| `49805b99-1710-41e5-bb49-1bfeee9fb643` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 07:08:09.662576+00:00` |
| `67f2d113-9846-486f-bb21-33fc850401be` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 07:08:10.740206+00:00` |
| `f16b5c9e-098c-4b69-bed0-0f3653b8a4f1` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 07:08:11.630311+00:00` |
| `dbc2dc6f-4e4a-48fe-b7bc-e96830f5ff57` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 07:08:31.328206+00:00` |
| `6b1cc21d-2cf3-4820-abb2-9a4e6d9c9eac` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 07:08:45.647832+00:00` |
| `e65d71db-cef8-4482-8739-5c8a82ba513e` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 07:08:46.226666+00:00` |
| `410fa2a4-b974-4237-8bcb-c027014fbb5c` | `phase3-67f4525a-4915-43a5-a4b9-2c3851e17677` | `CREATED` | `None` | `None` | `2026-10-23 07:22:57.507132+00:00` |
| `68e5a66a-bb0f-48ff-9990-e662a5eece52` | `phase3-2000620f-e6d8-44c1-b2bc-ddeb61993f93` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:04:44.513090+00:00` |
| `16b7599d-255d-4b2d-8f6a-fb5cb3b03bda` | `phase3-71b727e5-3844-42d1-a8b5-05d25ef5e06c` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:08:46.758541+00:00` |
| `82e01790-39c6-4a82-9c50-8266e7dc3004` | `adversarial-c073a38f` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 08:01:14.398905+00:00` |
| `4d3be5ef-e6f4-47ac-acf5-10215d07aa67` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 08:21:16.302905+00:00` |
| `18d18a6c-8fbc-4267-8555-206c2b2da01c` | `adversarial-d016f6c5` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:52:52.173920+00:00` |
| `90726022-d101-4dcc-8292-a8405de6b022` | `phase3-86c24671-b975-4407-9389-24e39bbe6b16` | `CREATED` | `None` | `None` | `2026-10-23 07:08:48.611635+00:00` |
| `0b542a0e-31ee-49ba-a7f4-57b3ad9b557f` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 11:16:08.062597+00:00` |
| `b2b12621-fa02-441b-b50d-50b99e177b18` | `Gate Decision Integration Service` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 07:42:06.889207+00:00` |
| `ae9b582b-d88e-411a-a2e5-b5bf5c34e7e1` | `adversarial-96abce94` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 07:42:07.483367+00:00` |
| `6ba14b92-582e-44e7-994b-5dccbac02188` | `phase3-dc792678-0b74-4384-b331-672ef1ec9929` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:12:05.434883+00:00` |
| `d048b181-9a22-4cbb-a061-41d82057907d` | `supervisor-e2e-0d95484a` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:48:08.398487+00:00` |
| `040a905b-6706-473d-8cee-962cd73b48a2` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 07:42:33.023884+00:00` |
| `7fe04b3d-3352-4535-b2cc-0e5270f5072e` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 09:50:55.356874+00:00` |
| `35e2f498-e890-4959-8472-e26c2337dfb5` | `supervisor-e2e-7b571946` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:08:58.274788+00:00` |
| `99a6aa48-2a3c-4adf-9216-89327fd4776e` | `Gate Decision Integration Service` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 09:31:54.379947+00:00` |
| `cd661eea-fcd5-48c3-be71-b72ef31da378` | `adversarial-e4609647` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:32:03.958661+00:00` |
| `c7b6a9ec-2a1a-414e-beee-f10c7b90fa87` | `supervisor-e2e-b30af2ae` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:53:13.244490+00:00` |
| `d413feca-db05-4533-b1a0-8c2ed881222f` | `supervisor-e2e-688d2468` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:20:29.492972+00:00` |
| `20b67937-79e2-4656-ac49-c71f0eec1e04` | `Gate Decision Integration Service` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 07:21:51.197915+00:00` |
| `69d61930-8c8d-48c8-a751-d6af58a62c3f` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 07:21:54.172910+00:00` |
| `9011799c-22f5-42ee-8274-d60ee0bad186` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 11:16:09.670667+00:00` |
| `b4468d05-861b-48ce-a09b-18c42054286e` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 07:42:27.324134+00:00` |
| `77fdac52-0fc1-44f4-a64a-aa2811a70f78` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 08:21:17.285261+00:00` |
| `cb8797ea-6255-498f-9333-02fb2174bd29` | `adversarial-81e36aad` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:50:48.006267+00:00` |
| `ad6f8462-a947-4ca0-a577-44b5e5b60f7c` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 12:05:36.078538+00:00` |
| `202f9e81-6c9a-4266-a6c1-06f099fd392d` | `Phase 6 real acceptance - integer calculator` | `PAUSED` | `None` | `None` | `2026-10-23 12:03:32.045554+00:00` |
| `a8a6b679-c506-453f-88ab-8a8b604c64c5` | `phase3-0c599191-36c6-4703-b779-ec86da147e93` | `CREATED` | `None` | `None` | `2026-10-23 11:16:45.334019+00:00` |
| `220479ee-3ee4-4c7c-943e-f571beee7e2c` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 12:06:28.623388+00:00` |
| `4b8993f7-6fe0-4d1e-adc8-34eda9b4bfcb` | `phase3-b9ee88ab-a6ab-4465-9734-d4d8011920e7` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 12:06:31.252381+00:00` |
| `6ee2637f-61c8-40bc-b8a6-38e6a8458c8d` | `phase3-8353fd62-dc9e-4a1b-8cbe-3d6e28f62397` | `CREATED` | `None` | `None` | `2026-10-23 12:06:36.000238+00:00` |
| `500b1567-9ec4-41c4-b9f7-fc40a56720b9` | `adversarial-b3effc02` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 09:32:00.168415+00:00` |
| `f90662bd-8801-4701-addb-81f66f859bf8` | `phase3-7b882d47-20da-49d0-a4c1-d4e82bfdd653` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 08:13:36.170502+00:00` |
| `6ba74bcd-dfda-4872-8c3d-f2f5113df24f` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 07:43:16.453871+00:00` |
| `78284606-ab55-4d0d-b9a0-83cf2724f8b4` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 07:42:55.176366+00:00` |
| `707be30a-2a51-4dc1-808a-aa726841208e` | `phase3-ea2863fd-4fed-4b8f-aa37-9c54f692d74d` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 09:04:45.872867+00:00` |
| `0f065b18-84eb-4a55-adc8-3c04a2aab1ca` | `phase3-5ebce4be-c008-4e24-9da2-da8b1769c681` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:53:13.852515+00:00` |
| `bd2057da-0267-490e-8429-bba6c535cb58` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 07:22:08.159912+00:00` |
| `036f68c9-e843-4b70-b5a9-ea84c8bac44a` | `adversarial-ff5b48bb` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 08:02:03.988565+00:00` |
| `0fb30d66-8f62-454c-bb80-ea59ae1deab4` | `supervisor-e2e-6742b579` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:52:24.565191+00:00` |
| `284dbf7f-95f2-4db8-8391-696c480d6b1d` | `adversarial-b6230d3d` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:37:38.362128+00:00` |
| `d8880e34-35d8-4626-bcb6-2c9747b46c63` | `phase3-176b1dd9-76b7-44d4-b569-5032622155b0` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:10:25.064416+00:00` |
| `48294a22-c981-41e6-a885-eca82a2d4de2` | `supervisor-e2e-061193fe` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 11:17:28.883234+00:00` |
| `30a45317-b02a-4b64-9d0e-b20f7c7bd6dd` | `supervisor-e2e-072e3970` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:43:32.508730+00:00` |
| `a2c664a9-4103-40fc-b2a3-15677701804f` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 07:22:09.638814+00:00` |
| `facced3c-b7c4-456b-8a93-46f1db8fd65d` | `supervisor-e2e-7664aeea` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 08:02:28.870622+00:00` |
| `6ed64b99-97c2-461a-8f5d-634ca03d9f50` | `phase3-f24c522c-83fe-41af-b159-f128cd68f7f2` | `CREATED` | `None` | `None` | `2026-10-23 08:02:31.432912+00:00` |
| `afc83f5f-eaf6-4ae9-9db4-5c39f22c849a` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 08:21:19.321184+00:00` |
| `594cf6b5-3062-4b15-abf4-dfdd3ae1158b` | `adversarial-941cf762` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:52:31.691266+00:00` |
| `623537b9-80b7-49d3-838f-9e45b73382ea` | `phase3-264c63c5-116d-4442-947a-d3d7780e2a13` | `CREATED` | `None` | `None` | `2026-10-23 07:43:20.672171+00:00` |
| `7b47f52e-3b12-4114-b352-a250583588f5` | `full-diagram-2568ea6a` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 08:11:32.350074+00:00` |
| `22618e95-2944-4628-ab86-52b17bd7d44a` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 07:43:17.273873+00:00` |
| `5c74458f-6c13-4556-ba2b-b85750b27759` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 07:22:10.790303+00:00` |
| `0e90865d-32e9-428d-9486-7b77a5d4edfa` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 07:22:13.238254+00:00` |
| `44cf30f6-db82-4d3d-b589-90fd070422b1` | `adversarial-89cc674d` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 07:52:49.188024+00:00` |
| `36f1b2a6-0bb8-45a9-99ad-34c60876faca` | `adversarial-21f1d6e2` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 08:01:17.765639+00:00` |
| `421c50ef-351c-4b70-890a-5894a5674330` | `supervisor-e2e-981882a1` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:39:40.383902+00:00` |
| `680582dc-10a4-4a0a-972c-9d074c676dd7` | `phase3-5a5571a9-d376-47dd-ae10-fbcc14cd5452` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 08:02:29.491869+00:00` |
| `82737a34-b15b-42a9-9e5e-59879e264d32` | `phase3-83c90c5a-b338-4ce2-9ce4-256fc48b9df8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:32:56.277116+00:00` |
| `c6fe2c7e-3ad7-4e8a-81a2-db851ea52bb0` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 09:32:22.248497+00:00` |
| `8d867612-8c87-4db7-a77c-ab7aee456d8e` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:32:55.027350+00:00` |
| `b2276907-768f-4eba-856a-0290cbef1eec` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 12:15:27.543883+00:00` |
| `0afbb85b-8d67-46f1-aac8-a387b393d255` | `phase3-aa605431-a4ca-4a2f-a78e-e7afa714de9d` | `CREATED` | `None` | `None` | `2026-10-23 09:32:58.608206+00:00` |
| `a0aca438-3ae5-4c2d-9bde-00ad852397bd` | `adversarial-13975de0` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 08:02:00.918215+00:00` |
| `6096e59a-a3d0-46b2-b345-4be364065c86` | `adversarial-b622ee03` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 11:15:48.097761+00:00` |
| `676ef6c2-8b32-487f-943a-d8f9ed53b448` | `phase3-648c6525-99de-4086-a86e-f81d936b2e36` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 12:16:33.843032+00:00` |
| `bf5ce549-b7fc-4e4b-9832-32e05e2432c3` | `adversarial-e077a2ce` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:42:10.576834+00:00` |
| `18524699-8754-49f0-a841-5d019334b8a7` | `supervisor-e2e-db93080f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 07:23:08.752998+00:00` |
| `7ddfa162-d27d-4217-9e60-ce5fa56ab216` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 11:16:28.519735+00:00` |
| `e9a9ca4f-2f47-4602-82c0-c32156d1214f` | `phase3-1902f2a2-8b83-4745-8f3a-02674bd291a0` | `CREATED` | `None` | `None` | `2026-10-23 09:04:48.710430+00:00` |
| `9ef0a398-fabf-49c9-a231-ba29e24d6ce7` | `phase3-a7e435bb-3b47-49d1-b9a2-2374c68a2547` | `CREATED` | `None` | `None` | `2026-10-23 07:53:15.667669+00:00` |
| `754898a7-95c4-44b7-9569-bf702439f237` | `adversarial-82896854` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 08:13:22.326621+00:00` |
| `a517b9e7-74e4-4920-ae07-f38d10ffec15` | `adversarial-e8049119` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 08:13:25.690555+00:00` |
| `013f071e-3734-4e38-859f-9a9a4424cb26` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 08:21:37.908935+00:00` |
| `b8c47f51-ff39-4258-bc5d-35d47fffdf2e` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 09:32:12.169792+00:00` |
| `f356e478-39e8-4026-8258-4d5600912539` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 09:32:23.460298+00:00` |
| `6525f3af-e4f7-4b29-a950-f0643e9ac70a` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 09:32:55.756279+00:00` |
| `4e0570ee-8d7d-4aba-9fff-1e5a67806d76` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 08:22:00.358290+00:00` |
| `5e1dbc40-aefc-4487-ad40-4681432197ba` | `supervisor-e2e-1da487bf` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 11:08:18.612380+00:00` |
| `b3886964-2207-4a41-8e1b-a12a160285f8` | `supervisor-e2e-1bea8ba1` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 12:17:37.727142+00:00` |
| `7d3290b0-64a4-47d4-ab4b-be27fa49b4d4` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 10:46:53.232641+00:00` |
| `c81fe7ec-e0d1-435a-99be-a7387bd79b0f` | `phase3-4e11cceb-a2cd-477d-b62e-9f7b28d2ce67` | `CREATED` | `None` | `None` | `2026-10-23 09:12:07.391541+00:00` |
| `564df8ff-3eb4-484f-8a2a-e23baa80ce6a` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 12:15:39.160495+00:00` |
| `533a6252-f91e-4861-a363-7c4929f3e331` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 09:51:03.238939+00:00` |
| `a725608c-caf1-41f2-9f45-21dc08fb8daa` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 08:22:12.359826+00:00` |
| `c188e7c5-9913-41b4-a05f-6022f6d791b9` | `neg-untested-f4685f` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-27 08:38:12.707888+00:00` |
| `a16bde62-d1f4-4906-ba13-2dc98e264936` | `phase3-f695d7c7-263d-4932-a1f3-6e07aaa93b0b` | `ANALYZING` | `None` | `None` | `2026-10-29 13:00:06.606164+00:00` |
| `a19486de-9279-4158-89b3-b1400b2d4a14` | `adversarial-39c8ac16` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 12:15:16.932236+00:00` |
| `da046cc6-cabf-46b5-8251-2d1965f2af5a` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 12:15:40.979579+00:00` |
| `17b47e13-752f-4704-8655-f8db393ec37b` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-27 09:56:56.715063+00:00` |
| `6bc80977-7252-41dc-98e5-552904335f3e` | `phase3-b83c4f1f-12d6-495b-8ec8-f43ffdd669a3` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:53:17.587539+00:00` |
| `dbc39bdc-ccef-48e9-91f0-b4d58d706303` | `phase3-952fbfca-c39f-4e8f-9052-4942e58fd378` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:32.304141+00:00` |
| `5f0bc375-4ad9-43b6-8b70-673127294170` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:32:41.431164+00:00` |
| `0279fdc7-d6d0-4d37-97fc-24e576cef47c` | `neg-empty-4e216a` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:04:52.296159+00:00` |
| `7be5fdba-81b6-4484-92e9-1c9bbeb06516` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 09:51:04.216555+00:00` |
| `d4a91c56-2eb3-469c-9dc4-df4287774b46` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 12:15:42.299325+00:00` |
| `6fcd8c7d-3460-4a66-8975-f0377d86cb86` | `phase3-7de94b7c-b8bd-43bd-a680-0fcddc632f18` | `CREATED` | `None` | `None` | `2026-10-23 09:51:35.911154+00:00` |
| `e16013b8-1d26-4aa9-a5be-38e2f1a74b6e` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:56:37.883915+00:00` |
| `1e29d15d-f2ae-4cae-ae6e-f277360ebf25` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 09:56:01.590800+00:00` |
| `2d136597-6e1c-46a8-a45d-7c8517339efb` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 09:56:38.721885+00:00` |
| `2bf005b6-f144-4d36-96fd-d2f9cdb02bcf` | `phase3-6ccbf799-9edb-44b9-a656-855a9140d093` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:56:39.183629+00:00` |
| `9db78187-8eb8-4e38-8592-d9a8182da415` | `phase3-c0446378-3ebe-44ae-aca1-fe03421ad5ca` | `CREATED` | `None` | `None` | `2026-10-26 09:21:33.159909+00:00` |
| `dcd41833-b880-4e54-85ab-24ef65e25f06` | `neg-empty-735062` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-27 08:38:12.797113+00:00` |
| `09ec052e-dca8-4a53-8793-a9f3c0b3540f` | `supervisor-e2e-5c735066` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-23 09:33:02.226020+00:00` |
| `79c630b9-0be7-41eb-a702-8377f1ae2457` | `neg-untested-d24069` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:52:23.348835+00:00` |
| `35f236aa-10fe-4b60-a332-942c28597cbb` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 09:51:05.224469+00:00` |
| `16666e55-775b-4aef-9e4f-89bcee5b63a4` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 12:15:44.955647+00:00` |
| `c891baa6-83c3-44b8-9581-c4190ab7bc33` | `supervisor-e2e-45cd87dc` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:33:05.692055+00:00` |
| `735370e6-3a7b-45f2-b239-865424d99dd6` | `phase3-ddfbbdf5-2194-4685-b4a4-51ab54c65b13` | `CREATED` | `None` | `None` | `2026-10-23 12:16:36.563328+00:00` |
| `499442d0-6a68-4d4a-9927-dc67f14291d3` | `adversarial-500de5ef` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 09:45:58.052491+00:00` |
| `866028da-3ee6-48a7-979b-b1db5768241d` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 10:47:02.122682+00:00` |
| `71783e94-b0e9-454c-b96c-60d45434d749` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 11:16:42.070833+00:00` |
| `98ae9afd-7a8b-4a68-aee8-12a4a47a68f9` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 10:47:23.555693+00:00` |
| `044e5674-0031-402a-b748-e6888b8d9a55` | `adversarial-c8203cae` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:46:01.119975+00:00` |
| `28e80ebb-e8d1-4c2b-b24d-b6d6259cdbb4` | `Intake Route Test Job` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:37:31.219860+00:00` |
| `9f2967df-e003-47e1-b9d2-4cd7724019d1` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 09:46:08.369600+00:00` |
| `85a6e138-3a96-4858-863d-97da89a564db` | `neg-untested-32d8c4` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:38.473770+00:00` |
| `6d7a446c-9477-45b7-9bc9-dcd66a09c767` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 09:51:07.076872+00:00` |
| `7d67e5ab-87a9-4127-bfa9-a5950f38e4ff` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 09:46:16.253760+00:00` |
| `6eb7ca88-454a-4657-b262-031cdb90ec45` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 09:46:17.436329+00:00` |
| `77352b71-5bb5-4332-990e-8199d03f3ebd` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 09:46:18.857082+00:00` |
| `91ffb8b1-5588-4da9-9e1e-8a9388aba5e1` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 09:46:20.706725+00:00` |
| `79001d65-efe3-4f96-af15-e2f3a2d7a582` | `supervisor-e2e-d71c80b0` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:47:06.901627+00:00` |
| `c5489ea0-018d-4596-b682-2beb453854cf` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 10:47:37.629854+00:00` |
| `b8ff6ab6-39c4-46fe-8cfe-3652dcaa60c6` | `phase3-a85de158-d382-4d35-9ba1-75349b0286a7` | `CREATED` | `None` | `None` | `2026-10-26 11:54:38.209031+00:00` |
| `8a971866-6531-4398-929c-6f76b267cf49` | `phase3-28a766d0-87cb-4785-b5f0-c3d7ebc75974` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 12:30:16.844081+00:00` |
| `242419d3-b21b-4a73-b76d-cad4c9223b02` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:46:33.795110+00:00` |
| `1fa3d936-6a48-408a-a3ec-ae2c01c467dc` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:46:46.352148+00:00` |
| `aed9888f-edd4-43a8-a6f9-30994d9378d2` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 09:46:47.199159+00:00` |
| `8d89a11d-5242-4af2-b0dc-9ec64930d52f` | `phase3-b9eef7e3-5e3e-48bb-a062-df8e9f341d02` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:46:47.833215+00:00` |
| `4463cbb3-971e-460b-a383-83fc8632f58b` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 10:47:03.463138+00:00` |
| `4b724f1e-b941-41fe-aac9-31087917de99` | `phase3-f235841e-1e02-47e7-bb0b-14591bfe0c8b` | `CREATED` | `None` | `None` | `2026-10-23 09:46:50.744453+00:00` |
| `61aa2dbc-3a06-44fe-8945-55b4d7b23265` | `phase3-209feac0-3236-41e0-b530-9060463569a6` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:51:34.362102+00:00` |
| `234d8de9-412b-44f8-963e-720e461ff44f` | `phase3-compliance-a22691c6` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 12:24:27.661156+00:00` |
| `beffca47-7790-49c4-bff7-5a58f5df3edb` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:51:21.517489+00:00` |
| `f2d4204b-2ed1-453e-9de9-458e834460d9` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 10:47:05.010732+00:00` |
| `b7206f8d-02c0-451b-bbe5-7c1e33e1a656` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 12:06:29.918743+00:00` |
| `dcc8714e-55ea-4c86-90a2-98351a8c611e` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 09:56:04.669592+00:00` |
| `d1f60fdc-981c-4d90-9c28-4617e8618d12` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 10:47:36.841017+00:00` |
| `ac7e0856-feb2-438a-b844-f6b1b21fdd1c` | `supervisor-e2e-704bcdc8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:53:33.262219+00:00` |
| `2d5be0d2-093a-4939-a374-d6291ec74d79` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 11:16:42.721197+00:00` |
| `76474646-6f46-4d73-8b43-845e2facf423` | `neg-empty-43eb44` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:38.807183+00:00` |
| `48e82d6a-4335-432f-9491-0c9fcb66bb49` | `phase3-f30df128-8126-49c8-b250-551efb3874b2` | `CREATED` | `None` | `None` | `2026-10-23 09:56:41.332153+00:00` |
| `15764ddd-2326-4931-93c4-5af794b8df58` | `adversarial-b0c23d59` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:04:14.367669+00:00` |
| `dc12d0d3-e7b5-4b58-94d8-88372ecb1fd3` | `supervisor-e2e-d25786c2` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:56:54.006430+00:00` |
| `117084df-b7ca-4e52-afbb-db113b5041c9` | `adversarial-91627a32` | `AWAITING_GATE_G4` | `None` | `None` | `2026-10-23 09:59:14.277851+00:00` |
| `a137a8e0-b9cb-4fe7-a0ec-9a923cac4d39` | `adversarial-47d1c6ad` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 09:59:17.415158+00:00` |
| `34f99cd1-b567-46ce-82a6-244f53bb0ab4` | `neg-untested-e956e1` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:04:52.498950+00:00` |
| `fe6b572d-a73d-4ce6-8e76-32cfc78cc7ff` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-23 09:59:33.850243+00:00` |
| `be9452bc-bf7b-4d38-97aa-b3f1d381f4d2` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 09:59:35.579651+00:00` |
| `dcdb27ab-5498-4ff6-bda2-8aa7cf0684fa` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 09:59:24.344909+00:00` |
| `9a25404e-bca6-46ee-8530-22998822e90b` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 09:59:31.708683+00:00` |
| `65a9ef7a-8039-478c-b23b-eec3c2f5ad25` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 09:59:32.807425+00:00` |
| `ba3113b1-8f23-4dec-b370-a5aed2372988` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 09:59:48.872378+00:00` |
| `1935a63f-6d29-4c70-81ae-52d2b97cac08` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-23 10:00:00.435545+00:00` |
| `4b0d062a-597f-4db9-86a2-1f6ad46908bd` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 10:00:01.131622+00:00` |
| `62975746-2f10-43b4-916f-87a1b555d51b` | `phase3-d97c0968-b3a2-4242-b551-53b366250903` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:00:01.646218+00:00` |
| `329111d4-e021-45dc-a9c4-58cce8ff15a0` | `phase3-1382a80c-5d68-4cdb-b748-220e3716f477` | `CREATED` | `None` | `None` | `2026-10-27 09:04:43.062419+00:00` |
| `891a29b0-98a0-4199-b12f-e0fe164fde12` | `test-p4-p5-8bdb43` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 12:24:27.810231+00:00` |
| `2ae6735e-aafa-4a64-a226-110a69892278` | `phase3-42f58b8e-7f1d-4767-9c2d-92beedf15ddd` | `CREATED` | `None` | `None` | `2026-10-23 10:00:03.412864+00:00` |
| `fc13cb9f-c3f4-4fdf-b245-392ec0171007` | `supervisor-e2e-c85e26c8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:00:15.218027+00:00` |
| `53e747b4-1b8a-4e74-a895-bad266689445` | `supervisor-e2e-ed2a309c` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:51:30.386731+00:00` |
| `ef3e0ea6-ebfb-4ce1-9f93-5487d257b028` | `phase3-compliance-d6e6cacb` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 12:24:27.826565+00:00` |
| `268a360b-2ee0-4c95-beeb-42578d6b6c7b` | `phase3-722a0fe3-f835-4523-a5c2-cef3bb727863` | `ANALYZING` | `None` | `None` | `2026-10-29 13:00:00.848665+00:00` |
| `a9791add-e8bd-4a10-b7f2-edbec05cfc3e` | `phase3-f9b4d541-45f1-47a4-b605-af891d427c37` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 10:47:38.377197+00:00` |
| `449afc35-c55c-4d02-ab47-a9df7a9c7b12` | `phase3-ce1422f4-dd23-421d-8b35-4c2cfec701b8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:31:39.138997+00:00` |
| `8477e350-f2be-4ea1-8690-fcf17406b20f` | `phase3-b41a2e36-872b-48c4-ac74-08566ce45c81` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 09:22:33.596235+00:00` |
| `f061ec34-1c62-4e22-8c6e-c9b1f5df683e` | `neg-untested-befcac` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:10.247837+00:00` |
| `b4bd0915-8695-431d-b831-3dab9bd6c1fe` | `phase3-fbacae04-1c00-43bf-bcdd-173846cc9c95` | `CREATED` | `None` | `None` | `2026-10-28 11:37:34.917865+00:00` |
| `89399c5a-6476-465a-9c22-481d51ccee77` | `supervisor-e2e-371ea626` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:05:45.274640+00:00` |
| `9327e1f8-58b9-4035-aeaf-0f558cf1cdb4` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-30 04:44:25.094473+00:00` |
| `fb6def00-58dd-4a5d-9fd1-279d6c49550f` | `supervisor-e2e-11de85f9` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:47:57.083525+00:00` |
| `cf2b501a-12b2-443a-94ef-a986d9cf9282` | `neg-empty-e92afb` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-27 05:51:43.542889+00:00` |
| `4cefc8ad-1840-41de-9ccc-b2f6b64aad76` | `phase3-c2019f9f-a6ab-4371-9bea-5fa44d8750db` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 05:53:02.148887+00:00` |
| `581c93a0-b14e-463a-b7f1-2743036145ce` | `supervisor-e2e-4e861b63` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 10:45:43.311727+00:00` |
| `831d59f9-f132-4fe9-92b9-f7683772ae9a` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-30 04:44:29.534026+00:00` |
| `393fb2b1-1bbc-46ca-9bbf-89e850d46ab3` | `adversarial-fba23e0f` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:30:47.959053+00:00` |
| `c9470a82-5ebe-4668-9e1d-6a07d9ed38c6` | `adversarial-751fedb5` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 11:06:52.995619+00:00` |
| `c08cb700-6bf8-40a4-8e19-767558903d1d` | `phase3-dfaf560c-fac9-4080-b4f6-e9151a9921f2` | `CREATED` | `None` | `None` | `2026-10-26 12:30:18.810081+00:00` |
| `7c687e3a-7cf2-47bd-b054-cc36f3b0ead6` | `supervisor-e2e-02a6e42c` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-26 10:45:43.290813+00:00` |
| `829ba3d1-18b0-45ab-9aed-7a2b38eff059` | `supervisor-e2e-b9b8f5c5` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:14:17.773921+00:00` |
| `6e526e85-2f32-4745-8605-60e592bdbef9` | `supervisor-e2e-c6457189` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:00.741665+00:00` |
| `937296b4-ba03-44b6-8d8d-135cd0f4c017` | `phase3-66f2eaf2-b6c0-4868-9066-0efa91f732a3` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 11:16:43.417690+00:00` |
| `c3c1a6e4-ed75-4329-aa22-12df44bf7e86` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-27 09:56:12.466899+00:00` |
| `451986fe-90c2-433a-9aeb-c225701314a0` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 12:05:28.878034+00:00` |
| `31574130-cba4-430b-a664-6a6cf0ca6523` | `test-p4-p5-a843da` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:02.628171+00:00` |
| `8835dc9d-2b92-4828-b395-3966bf3743e2` | `Intake Route Test Job` | `ANALYZING` | `None` | `None` | `2026-10-30 04:44:32.368631+00:00` |
| `62e79e5b-ae3a-4d88-bf20-d7bc4aa3e038` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-23 11:07:05.649802+00:00` |
| `af152435-2b66-4521-b8a0-af9a65eeed6b` | `supervisor-e2e-a855192c` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:21:45.423029+00:00` |
| `1f798aad-a821-4f97-96aa-fa76c2a537eb` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-23 11:07:15.413368+00:00` |
| `e64e8659-146e-4b78-a268-0785f2d3f38f` | `supervisor-e2e-d4121ac3` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:06:38.578715+00:00` |
| `4c81c298-4ac3-4a31-a895-d75456d7a8f8` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-23 11:07:19.479700+00:00` |
| `66860b0e-8f0f-4bbe-a503-4e647a47363e` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 11:07:32.334009+00:00` |
| `2e4f658b-9a73-44d9-b762-19befa22f30c` | `supervisor-e2e-952700bc` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:55:05.868068+00:00` |
| `6bc43011-3e22-46d3-ad79-1188a235cc62` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-27 09:56:13.349003+00:00` |
| `f8f27845-ea6d-4f6b-8a42-5840de0b383b` | `adversarial-c2798aa9` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-23 12:04:55.577802+00:00` |
| `2e24d2df-fcd4-416c-9922-bbd747c521be` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-23 12:05:30.585978+00:00` |
| `70339c4e-b58c-4429-9e15-31bb61501f13` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 12:06:03.957687+00:00` |
| `5845a7ce-4445-4926-9192-7e6147ed4093` | `Intake Route Test Job` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:47:12.175367+00:00` |
| `5a7bb5cf-b9fa-4419-8579-e68fdbeb640c` | `phase3-6649bfbb-a6a8-4af4-8ca3-c56c6de5d6a8` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 11:47:18.381635+00:00` |
| `e22ad4f2-0991-46be-bf6a-5b7bbe4615e6` | `supervisor-e2e-7b3e78a9` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 12:31:02.415762+00:00` |
| `cc424695-3972-41b8-bbe6-2bbf8526ffed` | `phase3-9cc47528-7cb5-451f-a95c-da83134bb39b` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:04:52.534623+00:00` |
| `801431ae-7d45-44f7-882e-ca114b4dc9fc` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-27 09:56:14.485717+00:00` |
| `7d57d686-9ac8-4403-98e7-a1fd82d9cee7` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-23 12:16:11.415666+00:00` |
| `6ec0d779-747c-4f7a-9724-1b5c3fdf304f` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-27 09:56:16.204735+00:00` |
| `c65d2a6f-4197-437c-bae6-9d6a6bbeec80` | `phase3-06d77823-fb79-4693-9d70-a496d4a8a17e` | `CREATED` | `None` | `None` | `2026-10-26 09:22:36.150180+00:00` |
| `6c62a962-d1b9-4d0a-b5a1-801025cc803f` | `Intake Route Test Job` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:47:30.380898+00:00` |
| `db14f529-f29b-441b-b1ff-294e95b72c4a` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-23 12:16:32.970467+00:00` |
| `baa4e73d-f823-41c7-9cc7-4cddd7131537` | `supervisor-e2e-9aca3843` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-26 11:09:22.452567+00:00` |
| `4f7c436c-7fd7-4530-8e32-8f3de552ea1b` | `phase3-compliance-f275e7ba` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 10:41:31.949069+00:00` |
| `e1d9b8f5-9bb7-43e9-b96c-b156f05757c4` | `phase3-d517366f-94f4-4eab-a93c-6727d67c6054` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 11:47:36.387493+00:00` |
| `924c59dd-fdd2-4688-ad14-f62ec7eac3a5` | `phase3-22592398-6756-4bc8-b4c7-69ad968c9f6a` | `CREATED` | `None` | `None` | `2026-10-26 06:01:52.302202+00:00` |
| `c582fe69-5955-4d9a-9b1d-c06832e9abea` | `phase3-58a8db73-1560-4803-95a6-4c49a4242f3b` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 11:55:34.909121+00:00` |
| `b430e0c5-dbf5-468f-99c6-dcc17d0e5eb1` | `phase3-compliance-0a861d47` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-26 12:15:34.632597+00:00` |
| `bca48ff9-258d-4cbd-bc1c-d584c1cdbcbe` | `phase3-327f19f4-de83-4e19-97be-a11993d0b045` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 11:47:53.456360+00:00` |
| `6b70f53d-3a8c-4902-a7f2-4b57f9a78e11` | `phase3-7d0a4b35-11c7-41de-b2ec-ffa9c7b57b17` | `CREATED` | `None` | `None` | `2026-10-27 10:31:41.457946+00:00` |
| `a1f99454-23e8-4310-ad16-41e9c863c77e` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-27 09:56:34.361507+00:00` |
| `c14e1d24-3fc0-4e86-b410-e7bc7989c9b7` | `test-p4-p5-a7ba0a` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:00.124056+00:00` |
| `896a76ba-93aa-4598-9eef-8107f45e8512` | `phase3-334cd1f1-db34-48f6-8bcb-f07e569a2b5b` | `ANALYZING` | `None` | `None` | `2026-10-29 13:00:31.237841+00:00` |
| `7749867a-abb1-4584-9c6d-06ed6c705a42` | `Audit Test Job` | `CREATED` | `None` | `None` | `2026-10-27 05:51:41.957225+00:00` |
| `24b8ab81-99e3-45d3-b333-68300b9ce6cd` | `phase3-3716412b-acd5-4d89-a79a-416861ec496b` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-27 07:10:51.836494+00:00` |
| `e46adfd4-6e0b-4846-9dc3-68c07d8884bc` | `supervisor-e2e-9a9ef825` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-27 05:51:43.770217+00:00` |
| `dbda576a-3438-4b32-a577-f57d317fc833` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-27 05:52:04.750422+00:00` |
| `c7a711b5-e00d-4e9f-9bbc-7e77d0911ec3` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-27 05:52:05.811252+00:00` |
| `d242d86d-650f-407b-894f-156f10e4e666` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-27 09:56:35.114852+00:00` |
| `1ced4879-e421-48c5-838e-20d7005d5521` | `neg-empty-947815` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:31.753503+00:00` |
| `ba515197-b6ab-4d30-bc70-b18a22a20c46` | `Alumaconnect Modernization` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 07:14:14.768119+00:00` |
| `672036a8-847e-4da7-b992-8a666441dba6` | `neg-untested-f506f9` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:37.679527+00:00` |
| `d853fb99-0781-479f-bdc3-9b73b010c71b` | `neg-empty-a270f9` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-27 08:38:12.692003+00:00` |
| `8030efaf-4717-4ddd-8d94-e948faddadb1` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-27 06:06:01.456006+00:00` |
| `e6f2da0a-a312-4a4c-a0b7-976cf19fb75f` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-27 06:06:02.943914+00:00` |
| `9f0dd0a8-8455-46f0-a5c5-37e7b1c9b2a0` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-27 06:06:03.991533+00:00` |
| `84cc3a63-f78f-417c-b83f-142d3b1d334c` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-27 06:06:06.098826+00:00` |
| `bca854c9-8a65-4505-9da9-d47b9af40836` | `supervisor-e2e-010d97bd` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:51.108016+00:00` |
| `70a8b7f7-5b31-4cd7-909f-a236e83f2df1` | `phase3-213f2d8d-3d02-4272-bfd9-626495a6cb20` | `ANALYZING` | `None` | `None` | `2026-10-29 13:00:38.750948+00:00` |
| `0126174e-e16e-4191-9299-fbc6edde1884` | `supervisor-e2e-eefb81f8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 05:38:50.897044+00:00` |
| `3f148d8c-8940-49d0-a748-d0ae30dd5354` | `phase3-bed44890-f51f-4f31-bd45-c990f00eed1c` | `ANALYZING` | `None` | `None` | `2026-10-29 13:00:27.467725+00:00` |
| `aae09477-5aa2-4962-839e-c43e09cf4d9f` | `phase3-77f12c8e-c4aa-4fb7-8b48-dd20aa45df03` | `ANALYZING` | `None` | `None` | `2026-10-29 13:00:15.541389+00:00` |
| `bd0c90c4-80f7-4838-a5d8-4057e128d7a7` | `supervisor-e2e-74628f6c` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:02.288888+00:00` |
| `7c817434-2d65-485b-ab6d-601572f2c7a9` | `supervisor-e2e-60fd62f7` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:32:24.268395+00:00` |
| `42f431e1-8bce-444c-bf2f-73059366129b` | `Gate Decision Integration Service` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:32:27.545065+00:00` |
| `fb65088c-bc6a-4099-9778-1902477e9305` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-27 10:33:32.414624+00:00` |
| `4055b2fc-1952-4089-9331-693a6cb7134a` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-27 10:33:33.550478+00:00` |
| `db895874-6c88-4a69-bdaa-8ca46a6784c2` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-27 10:33:34.301854+00:00` |
| `15f07d8c-1924-462e-8377-2f0292f88e5f` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-27 10:33:35.168031+00:00` |
| `509bc643-f548-407f-8930-57d9fd1a9bc3` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-27 10:33:48.186316+00:00` |
| `843096ca-b167-4e44-a2e8-91984ec1e7ab` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-27 10:33:48.899976+00:00` |
| `99d61766-d4f4-4150-80b8-f6b6e3f45e1d` | `phase3-5ee7b168-8d6d-4fc7-9d88-a33a1a202e2c` | `CONVERTING` | `None` | `None` | `2026-10-29 13:00:11.256106+00:00` |
| `3d2e453e-6c7f-4d4d-b34e-78930a05d97b` | `phase3-compliance-ec141bfb` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 05:38:55.052740+00:00` |
| `b157b24f-f104-424c-8643-f0113cf74176` | `phase3-83c145ae-176e-4000-9c43-9fabc305e6af` | `CONVERTING` | `None` | `None` | `2026-10-29 13:00:23.691253+00:00` |
| `a83b1765-596e-4e65-9696-681b2bf2f4bd` | `phase3-e0f81193-127e-4f26-b714-4e5f1e5fcca0` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:33:56.427009+00:00` |
| `cebeab96-3614-4e8d-a916-2ab1dec03148` | `phase3-2cb488e3-8bcd-411f-ae95-584e7679ff1b` | `CREATED` | `None` | `None` | `2026-10-27 10:33:58.650743+00:00` |
| `cd8f984b-7740-4d68-a947-f1cf7964ac3e` | `phase3-compliance-6b146ea8` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 05:39:03.752457+00:00` |
| `4c87507b-2cbe-43ae-81fc-63906678042f` | `phase3-9bc5d882-b694-47fd-8482-1ffa0b860a1c` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:07:49.743036+00:00` |
| `bf664a6f-d8ec-4faf-af83-b2486a92b234` | `neg-untested-b8bd93` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:04.209387+00:00` |
| `0bbf3e38-600b-46ad-83de-b09131da9c7f` | `neg-empty-329b2c` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:04.165800+00:00` |
| `1799aaee-7115-4da9-957b-48f50488aa47` | `Private Repo PAT Intake Test` | `CREATED` | `None` | `None` | `2026-10-28 05:35:02.221961+00:00` |
| `1e502c75-9eda-4c98-a49c-7ce5bb7d102d` | `test-p4-p5-12783d` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:01.861999+00:00` |
| `b44b2e95-c120-42b6-a23e-9165859e99e4` | `adversarial-dde2c16f` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:34:20.495003+00:00` |
| `1147b827-60ee-4061-8fa4-6d8d0d2dff97` | `phase3-64e7e2a8-fe37-440c-be06-d9f3d44b8476` | `CONVERTING` | `None` | `None` | `2026-10-29 12:59:55.858534+00:00` |
| `0602d371-1dbf-4033-93e3-65c21a04a084` | `Intake Route Test Job` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 06:38:35.470824+00:00` |
| `0043850a-dc06-487f-b99a-ac7ae7135e22` | `phase3-b9bd6c96-64fd-4ca3-9741-1dc6c0275af4` | `ANALYZING` | `None` | `None` | `2026-10-29 13:00:42.653056+00:00` |
| `7e6971fb-0d1c-4916-b459-5246e3b582f9` | `neg-empty-fe1620` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:37:50.632278+00:00` |
| `349f0726-324b-4476-903c-4d9f51005b83` | `phase3-a67fd9f9-55bd-4e2a-be8d-bb382792ca33` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 11:48:11.268220+00:00` |
| `a858e713-a9d8-43b2-89ae-85edf881e8b6` | `phase3-b983ba9f-db0a-4928-8b9b-51c2e325f97a` | `ANALYZING` | `None` | `None` | `2026-10-29 13:00:19.927947+00:00` |
| `daa55c87-7d88-478e-a29b-c9eb80d39723` | `supervisor-e2e-a9668ff1` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 05:39:07.400376+00:00` |
| `2e723d40-8446-4316-9854-351b39e9e07d` | `phase3-compliance-38250a18` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 05:37:55.370417+00:00` |
| `1d06848d-6e29-4e46-b696-58b36c55d9e2` | `phase3-bc0b3fd2-9a9f-4c02-8971-51a2a8971825` | `CONVERTING` | `None` | `None` | `2026-10-29 13:00:35.031388+00:00` |
| `fd4a0845-18df-43b4-b1f5-033c90f30c57` | `supervisor-e2e-86c0aa8f` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:07.445688+00:00` |
| `36a99f0d-cc9a-4925-8fbf-40fe79dd268f` | `supervisor-e2e-e019360d` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:01.463942+00:00` |
| `045eda51-5758-4d76-855e-469be90aa410` | `phase3-7005c683-e90b-47a8-b2f2-a927d7de80fc` | `CREATED` | `None` | `None` | `2026-10-28 11:07:55.590756+00:00` |
| `696177b2-17e5-4704-bb2b-adff69dc7ae1` | `supervisor-e2e-dba8f16d` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:34:41.923380+00:00` |
| `9eaf6202-1265-4103-9f90-8b50791a4805` | `neg-untested-75187e` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:37:55.623097+00:00` |
| `efd27cb2-0927-46ec-8ecf-546cdd4db81f` | `neg-empty-413ae4` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:37:59.155432+00:00` |
| `b6ac1604-0e91-4c14-9d03-95d9bfa2d5fa` | `Trusted Origin Job` | `CREATED` | `None` | `None` | `2026-10-27 10:36:32.050544+00:00` |
| `33225143-a689-4339-b12b-f97aed3f29d9` | `User A Confidential Job` | `CREATED` | `None` | `None` | `2026-10-27 10:36:33.058016+00:00` |
| `ed8b69c3-7c2d-44ac-a73c-d569e17203a9` | `Audited Project` | `CREATED` | `None` | `None` | `2026-10-27 10:36:33.831661+00:00` |
| `2975c418-05dc-40bb-ad94-8136f84bece0` | `Atomic Transaction Job` | `CREATED` | `None` | `None` | `2026-10-27 10:36:34.529988+00:00` |
| `aa677e59-ee5f-42c4-9177-9febe381af95` | `phase3-3ccab5af-8c4f-4900-b64b-67801706b65d` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:12:26.111858+00:00` |
| `2697c96a-bc66-4ba9-88fa-5e0dd2e81dae` | `phase3-compliance-1a422d64` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 05:39:12.063146+00:00` |
| `54969dee-74ff-4b66-9dc9-2c954f55f5e4` | `Phase 2B Test Job` | `CREATED` | `None` | `None` | `2026-10-27 10:36:49.305783+00:00` |
| `bcc3b695-0660-4a7f-b3f7-6a76e363d828` | `Phase 2B HTTP Job` | `CREATED` | `None` | `None` | `2026-10-27 10:36:49.928160+00:00` |
| `ac3e2e54-6834-4583-9b21-c19f5ccde473` | `neg-empty-b3311a` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:02.083546+00:00` |
| `3b4eeb4e-2a9b-450a-9dea-0f132a847fcd` | `neg-empty-0f4720` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:09.817176+00:00` |
| `6c6f4174-65ec-413a-adf8-a1f0a4547cb7` | `test-p4-p5-f88cac` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:03.023713+00:00` |
| `db9d9a5f-1f4d-4376-913f-ce6ca9c101c1` | `phase3-e47f497e-eee6-4eca-a42b-e7153626a25a` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:36:57.714945+00:00` |
| `8fded22b-39b1-40ea-9774-1da4821caf30` | `phase3-34556653-f940-4ea2-ac17-94513c7fb799` | `CREATED` | `None` | `None` | `2026-10-27 10:37:00.329158+00:00` |
| `4e935657-0bb2-4411-9530-71846912e560` | `test-p4-p5-dea463` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:00.573830+00:00` |
| `df5144e8-6e78-41f1-beb6-69065df1b74c` | `test-p4-p5-11479b` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:00.926054+00:00` |
| `27d04aea-d45c-4876-8fd8-0768a21e2ecb` | `adversarial-e6f2df7e` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:37:19.774357+00:00` |
| `8c5a83cd-e473-48fa-819a-29384150d697` | `phase3-24fcba7e-fcd9-4f46-9332-5dd00364b4c9` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:00.448520+00:00` |
| `1bb667b7-b7ee-4e5f-9786-3179f65ec2b9` | `phase3-9774e35e-a94e-4f11-8ac8-ed76ae6ec726` | `CREATED` | `None` | `None` | `2026-10-28 11:12:32.491158+00:00` |
| `3911fe74-46bd-49dd-8313-b2bf4e80d757` | `supervisor-e2e-a808cda1` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:39:19.482902+00:00` |
| `56175125-5d40-4c50-8ec8-aa703f143163` | `phase3-d0983895-acdb-48ca-b52a-8594f088e973` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:02.616933+00:00` |
| `8626cf4b-289c-4cb3-8937-5022797f49ec` | `phase3-compliance-1a1e85f1` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 05:38:06.920198+00:00` |
| `c9af61ce-f9e8-4cc7-a33f-0ada3a5af4a1` | `Gate Decision Integration Service` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:14:22.222687+00:00` |
| `75a4d477-6f92-425e-b447-3ed3903f1131` | `phase3-c4f309c7-cd59-44a0-887b-c2e5d81097bc` | `AWAITING_GATE_G2` | `None` | `None` | `2026-10-28 05:38:04.629038+00:00` |
| `1f416661-753a-46fd-8a80-a8df73996c94` | `supervisor-e2e-39bf70a9` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-27 10:37:35.830273+00:00` |
| `ad6f4a74-2dc8-4b17-96f3-2adc05676c6e` | `test-p4-p5-c92cf4` | `AWAITING_GATE_G3` | `None` | `None` | `2026-10-28 06:39:00.385899+00:00` |
| `0ece9902-aefe-4064-a7f3-a444e8f90e2a` | `Spendwise Modernization` | `AWAITING_GATE_G1` | `None` | `None` | `2026-10-28 11:17:06.255497+00:00` |

## 2. Gates and Decisions by State

### Workflow Gates by Type and Status

| Gate Type | Status | Count |
|---|---|---:|
| `G1` | `APPROVED` | 473 |
| `G1` | `NEEDS_CHANGES` | 1 |
| `G1` | `PENDING` | 177 |
| `G1` | `REJECTED` | 147 |
| `G2` | `APPROVED` | 402 |
| `G2` | `INVALIDATED` | 156 |
| `G2` | `NEEDS_CHANGES` | 2 |
| `G2` | `PENDING` | 112 |
| `G2` | `REJECTED` | 122 |
| `G3` | `APPROVED` | 338 |
| `G3` | `INVALIDATED` | 69 |
| `G3` | `PENDING` | 47 |
| `G3` | `REJECTED` | 39 |
| `G4` | `APPROVED` | 21 |
| `G4` | `PENDING` | 12 |

### Gate Decisions Recorded

| Decision | Count |
|---|---:|
| `APPROVED` | 413 |
| `REJECTED` | 308 |
| `NEEDS_CHANGES` | 18 |

### Gate vs Job State Contradictions

- Pending gates whose job is not awaiting that gate: **348**
- Jobs in `AWAITING_G*` status without a corresponding pending gate: **323**

| Gate ID | Job ID | Gate Type | Gate Status | Job Status |
|---|---|---|---|---|
| `52e45ef7-d52d-4ee9-a9aa-153751f70f6b` | `44ac6de1-55fc-4dd8-99cb-baf343d1d742` | `G2` | `PENDING` | `AWAITING_GATE_G2` |
| `7d4173ae-e119-4bb7-95d6-2b37784a11b0` | `a1076c96-965d-4a3a-b028-0364802c84ad` | `G2` | `PENDING` | `AWAITING_GATE_G2` |
| `ca8bc719-ceab-4605-8b1b-52107b7baac4` | `368a699c-1621-4e00-a405-b42bd51314d8` | `G3` | `PENDING` | `AWAITING_GATE_G3` |
| `484e1ab9-b9d3-477d-a61e-7a330a0c30d2` | `fbb8918a-6a98-4ffe-9980-f819d2f67358` | `G2` | `PENDING` | `AWAITING_GATE_G2` |
| `eb5adc47-da2b-4530-82af-354899d0c984` | `18accde1-3e62-4f9e-8e0e-afe188887317` | `G1` | `PENDING` | `AWAITING_GATE_G1` |
| `507b330d-0f3f-4874-a54e-5c10927c385c` | `5512a921-95c6-4d3e-b0de-d44189248e99` | `G1` | `PENDING` | `AWAITING_GATE_G1` |
| `c854d986-b55e-4ddd-9d68-45ed6365e616` | `6e9ac849-1877-4542-8adf-920269247764` | `G3` | `PENDING` | `AWAITING_GATE_G3` |
| `ef652dd0-122a-47f0-af19-8a6baf5710ce` | `cef9728e-d2e1-47b8-bbbf-e6938adbc3bc` | `G3` | `PENDING` | `AWAITING_GATE_G3` |
| `e4cb1a06-7079-4dfc-bfd9-91f103c9cd70` | `3c66741c-4d6f-44e4-829d-d2a6f0f194a2` | `G2` | `PENDING` | `AWAITING_GATE_G2` |
| `76747ebf-b8ae-478d-bbdc-ffd1109bbf62` | `547c1f28-7d70-4d5f-bb32-1d697f44f063` | `G2` | `PENDING` | `AWAITING_GATE_G2` |
| `af1a612d-e213-4c0d-903a-f866866e3fc6` | `cb528ac8-48ca-4104-880e-046040e8e1f2` | `G1` | `PENDING` | `AWAITING_GATE_G1` |
| `b4768322-c662-4063-8d2f-6f3b4ee5a912` | `7763014c-4320-4b69-967d-d728c1b8c446` | `G2` | `PENDING` | `AWAITING_GATE_G2` |
| `ccbb579c-d926-4376-8fb2-5a2be661ff6d` | `1257433d-98d6-4643-9c9b-50f4d1707d12` | `G2` | `PENDING` | `AWAITING_GATE_G2` |
| `f12add4d-751f-44cb-ab2e-58985845015a` | `3b41bf12-4afc-4e1c-8d6b-f6243ee9199c` | `G3` | `PENDING` | `AWAITING_GATE_G3` |
| `5a7e73bc-ffc8-4177-9d5e-0312885b1230` | `5d0caafa-7b6c-4f51-8481-f5896b31bb68` | `G2` | `PENDING` | `AWAITING_GATE_G2` |

*(Total 348 contradictions. Retained in evidence ledger)*

## 3. Modules vs Attempts Verification Records

### Module Statuses

| Module Status | Count |
|---|---:|
| `PENDING` | 661 |
| `VERIFIED` | 148 |
| `BLOCKED` | 78 |
| `COMPLETED` | 53 |
| `FAILED` | 49 |
| `PLANNED` | 14 |
| `GENERATED` | 3 |
| `MODULE_APPROVED` | 1 |

### Module Attempt Statuses

| Attempt Status | Count |
|---|---:|
| `BLOCKED` | 141 |
| `GENERATED` | 115 |
| `RUNNING` | 24 |
| `FAILED` | 20 |
| `VERIFIED` | 9 |
| `REPAIR_REQUIRED` | 6 |
| `ESCALATED` | 3 |

### Module Verification Integrity Discrepancy

- **Modules marked `VERIFIED` without a `VERIFIED` attempt:** **139**
*(Critical finding: derived verified eligibility exists without durable verification execution records)*

| Module ID | Job ID | Module Name | Status |
|---|---|---|---|
| `f05f0bd1-2190-4f2d-9c7f-b4f23f42fd1a` | `2aacd441-e107-454e-a21c-9b45c490bec6` | `auth_service` | `VERIFIED` |
| `b5d8f9be-c143-43cc-876c-8f08c5a8a669` | `818f71fb-7d32-44e4-8ec6-920f9983de65` | `M1` | `VERIFIED` |
| `be13082e-0b40-4707-9a54-59a6ad7047b4` | `818f71fb-7d32-44e4-8ec6-920f9983de65` | `M2` | `VERIFIED` |
| `39d5f011-48ac-44cd-b7ac-a0ba5a05b143` | `818f71fb-7d32-44e4-8ec6-920f9983de65` | `M3` | `VERIFIED` |
| `20538493-994b-4221-ae54-f6cffa8c6b81` | `18ba396c-bf48-4489-b9dd-55ed15a47897` | `M1` | `VERIFIED` |
| `399ebc0a-2e24-4568-8420-7bf940c18292` | `18ba396c-bf48-4489-b9dd-55ed15a47897` | `M2` | `VERIFIED` |
| `f5d60bdc-fd77-4742-acc3-01ddd0381b67` | `18ba396c-bf48-4489-b9dd-55ed15a47897` | `M3` | `VERIFIED` |
| `cd44e2d6-8c06-4b2e-8a54-723486aafce4` | `26fbcffe-c3ed-4c69-8acc-3dedc74bb0e9` | `M2` | `VERIFIED` |
| `d526762b-5737-4e1d-a3d7-5bf75c1d8aa6` | `26fbcffe-c3ed-4c69-8acc-3dedc74bb0e9` | `M1` | `VERIFIED` |
| `cec8843c-dd46-40ca-9544-99dccba7dba7` | `26fbcffe-c3ed-4c69-8acc-3dedc74bb0e9` | `M3` | `VERIFIED` |
| `cfec043d-292d-4b88-ae66-8ee3671583ba` | `4d9d33ae-0dbe-41ea-a3a3-651a63cdd1a7` | `orders_module` | `VERIFIED` |
| `2bad6017-8674-4461-b70e-dec04b515d62` | `ddb751a2-f227-4bbc-bed5-657ffb66dd82` | `M1` | `VERIFIED` |
| `5d49dcff-aa9f-41a5-b0fb-0d7ce2db38c6` | `ddb751a2-f227-4bbc-bed5-657ffb66dd82` | `M2` | `VERIFIED` |
| `a3a11a02-e6ed-4ef7-aa7a-acf82c3f3c7c` | `ddb751a2-f227-4bbc-bed5-657ffb66dd82` | `M3` | `VERIFIED` |
| `3889decc-44e9-452d-b917-dd41ed57f32f` | `863d548c-9c7f-466f-92bc-79a0ef598fe9` | `M3` | `VERIFIED` |
| `a80ad0b7-a5ab-4c0e-b1da-4e6ef5987abb` | `863d548c-9c7f-466f-92bc-79a0ef598fe9` | `M2` | `VERIFIED` |
| `c5a29da0-14b6-4428-9832-585c626b056c` | `863d548c-9c7f-466f-92bc-79a0ef598fe9` | `M1` | `VERIFIED` |
| `7bf94f04-b792-4a9d-afdb-62655d20b046` | `02f2a820-2d58-4f2b-8ed7-3132d89d2e15` | `mod_orders` | `VERIFIED` |
| `0497fc4f-ea0e-45e2-b217-8c1b8583b158` | `02f2a820-2d58-4f2b-8ed7-3132d89d2e15` | `mod_payments` | `VERIFIED` |
| `6dd64588-e025-4cec-a3f2-14d91b7d0c01` | `c5931fe1-fffe-421c-b4e6-d7c07ae06864` | `M2` | `VERIFIED` |

*(Total 139 modules listed in ledger)*

## 4. Active & Expired Leases

- Total modules with lease attributes: **120**
- Modules with expired leases: **99**
- Tasks table entries with leases: **4**

| Module ID | Job ID | Name | Status | Owner | Lease Expires At | Gen |
|---|---|---|---|---|---|---:|
| `b5d8f9be-c143-43cc-876c-8f08c5a8a669` | `818f71fb-7d32-44e4-8ec6-920f9983de65` | `M1` | `VERIFIED` | `None` | `2026-10-23 07:57:50.764008+00:00` | 0 |
| `be13082e-0b40-4707-9a54-59a6ad7047b4` | `818f71fb-7d32-44e4-8ec6-920f9983de65` | `M2` | `VERIFIED` | `None` | `2026-10-23 07:57:50.764008+00:00` | 0 |
| `39d5f011-48ac-44cd-b7ac-a0ba5a05b143` | `818f71fb-7d32-44e4-8ec6-920f9983de65` | `M3` | `VERIFIED` | `None` | `2026-10-23 07:57:50.764008+00:00` | 0 |
| `20538493-994b-4221-ae54-f6cffa8c6b81` | `18ba396c-bf48-4489-b9dd-55ed15a47897` | `M1` | `VERIFIED` | `None` | `2026-10-23 07:47:09.410893+00:00` | 0 |
| `399ebc0a-2e24-4568-8420-7bf940c18292` | `18ba396c-bf48-4489-b9dd-55ed15a47897` | `M2` | `VERIFIED` | `None` | `2026-10-23 07:47:09.410893+00:00` | 0 |
| `f5d60bdc-fd77-4742-acc3-01ddd0381b67` | `18ba396c-bf48-4489-b9dd-55ed15a47897` | `M3` | `VERIFIED` | `None` | `2026-10-23 07:47:09.410893+00:00` | 0 |
| `cd44e2d6-8c06-4b2e-8a54-723486aafce4` | `26fbcffe-c3ed-4c69-8acc-3dedc74bb0e9` | `M2` | `VERIFIED` | `None` | `2026-10-23 07:42:37.127247+00:00` | 0 |
| `d526762b-5737-4e1d-a3d7-5bf75c1d8aa6` | `26fbcffe-c3ed-4c69-8acc-3dedc74bb0e9` | `M1` | `VERIFIED` | `None` | `2026-10-23 07:42:37.127247+00:00` | 0 |
| `cec8843c-dd46-40ca-9544-99dccba7dba7` | `26fbcffe-c3ed-4c69-8acc-3dedc74bb0e9` | `M3` | `VERIFIED` | `None` | `2026-10-23 07:42:37.127247+00:00` | 0 |
| `2bad6017-8674-4461-b70e-dec04b515d62` | `ddb751a2-f227-4bbc-bed5-657ffb66dd82` | `M1` | `VERIFIED` | `None` | `2026-10-23 08:06:16.291358+00:00` | 0 |
| `5d49dcff-aa9f-41a5-b0fb-0d7ce2db38c6` | `ddb751a2-f227-4bbc-bed5-657ffb66dd82` | `M2` | `VERIFIED` | `None` | `2026-10-23 08:06:16.291358+00:00` | 0 |
| `a3a11a02-e6ed-4ef7-aa7a-acf82c3f3c7c` | `ddb751a2-f227-4bbc-bed5-657ffb66dd82` | `M3` | `VERIFIED` | `None` | `2026-10-23 08:06:16.291358+00:00` | 0 |
| `3889decc-44e9-452d-b917-dd41ed57f32f` | `863d548c-9c7f-466f-92bc-79a0ef598fe9` | `M3` | `VERIFIED` | `None` | `2026-10-23 08:07:02.845475+00:00` | 0 |
| `a80ad0b7-a5ab-4c0e-b1da-4e6ef5987abb` | `863d548c-9c7f-466f-92bc-79a0ef598fe9` | `M2` | `VERIFIED` | `None` | `2026-10-23 08:07:02.845475+00:00` | 0 |
| `c5a29da0-14b6-4428-9832-585c626b056c` | `863d548c-9c7f-466f-92bc-79a0ef598fe9` | `M1` | `VERIFIED` | `None` | `2026-10-23 08:07:02.845475+00:00` | 0 |
| `6dd64588-e025-4cec-a3f2-14d91b7d0c01` | `c5931fe1-fffe-421c-b4e6-d7c07ae06864` | `M2` | `VERIFIED` | `None` | `2026-10-23 09:55:46.764057+00:00` | 0 |
| `021b614e-d7a0-4bb5-a9fe-6c68897d4ac4` | `c5931fe1-fffe-421c-b4e6-d7c07ae06864` | `M3` | `VERIFIED` | `None` | `2026-10-23 09:55:46.764057+00:00` | 0 |
| `4c74e829-be20-4ba4-acf5-e78ba99441f9` | `4b9e9148-e273-425d-80eb-332abf3e1817` | `M2` | `VERIFIED` | `None` | `2026-10-23 08:18:24.485569+00:00` | 0 |
| `50ca7fa2-bb1e-4c8f-9d3b-5e08a10f84c4` | `4b9e9148-e273-425d-80eb-332abf3e1817` | `M1` | `VERIFIED` | `None` | `2026-10-23 08:18:24.485569+00:00` | 0 |
| `ce033c34-1f8a-4c4e-a16e-b308741c7173` | `4b9e9148-e273-425d-80eb-332abf3e1817` | `M3` | `VERIFIED` | `None` | `2026-10-23 08:18:24.485569+00:00` | 0 |
| `82c3eee3-41d9-47ff-a6dc-aa388d0ab0e3` | `fe4aded0-9bd8-43a2-b85f-75f20208bd66` | `M1` | `VERIFIED` | `None` | `2026-10-23 10:04:16.273014+00:00` | 0 |
| `4b1a8932-7460-44a1-bffe-a8f5c42fb40e` | `a6027238-9bbe-4ad7-93e8-66febaab2d81` | `M2` | `VERIFIED` | `None` | `2026-10-23 09:37:02.501498+00:00` | 0 |
| `865fb5b8-0e6d-440b-a7f0-790318611bdd` | `a6027238-9bbe-4ad7-93e8-66febaab2d81` | `M1` | `VERIFIED` | `None` | `2026-10-23 09:37:02.501498+00:00` | 0 |
| `3ae8e84e-79ab-42d4-ba0f-d886eb25a481` | `a6027238-9bbe-4ad7-93e8-66febaab2d81` | `M3` | `VERIFIED` | `None` | `2026-10-23 09:37:02.501498+00:00` | 0 |
| `51f002e2-4c10-4db6-b6ac-500bec6e3e08` | `c5931fe1-fffe-421c-b4e6-d7c07ae06864` | `M1` | `VERIFIED` | `None` | `2026-10-23 09:55:46.764057+00:00` | 0 |

## 5. Workflow Checkpoint Histories

- **Total Checkpoint Records:** **158,335**

### Checkpoints by Kind

| Checkpoint Kind | Count | Earliest Timestamp | Latest Timestamp |
|---|---:|---|---|
| `AFTER` | 4,035 | `2026-10-22 06:18:14.080968+00:00` | `2026-10-30 04:44:32.373639+00:00` |
| `BEFORE` | 3,717 | `2026-10-22 06:18:14.071032+00:00` | `2026-10-30 04:44:32.356787+00:00` |
| `INTERRUPT` | 987 | `2026-10-22 06:20:31.951625+00:00` | `2026-10-29 12:59:49.637649+00:00` |
| `RECOVERY` | 149,596 | `2026-10-22 06:20:32.103962+00:00` | `2026-10-29 13:00:40.603204+00:00` |

### Top Active Graph Nodes by Checkpoint Volume

| Node Name | Checkpoint Count |
|---|---:|
| `converting` | 38,262 |
| `intake` | 31,366 |
| `characterization` | 24,975 |
| `created` | 23,888 |
| `analysis` | 17,727 |
| `planning` | 6,879 |
| `conversion` | 2,734 |
| `analyzing` | 2,141 |
| `characterizing` | 1,776 |
| `failed` | 1,743 |
| `integrating` | 1,687 |
| `persist_result` | 1,451 |
| `verification` | 808 |
| `gate_g1` | 803 |
| `gate_g2` | 697 |

## 6. Outbox Counts and Age

| Status | Count | Earliest Created | Latest Created |
|---|---:|---|---|
| `PENDING` | 2,909 | `2026-10-28 11:40:54.981775+00:00` | `2026-10-29 13:00:40.612383+00:00` |
| `DEAD_LETTER` | 28,390 | `2026-10-26 11:27:02.028379+00:00` | `2026-10-28 11:37:34.981102+00:00` |

- **Oldest PENDING outbox event:** `2026-10-28T11:40:54.981775+00:00` (Age: **2,514.0 minutes** / **41.9 hours**)

### Dead-Letter Queue (DLQ) Error Samples

| Outbox ID | Event Type | Attempts | Last Error Preview |
|---|---|---:|---|
| `8a0a0a1c-dd53-4365-b6b8-ea9b08fb3b0d` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `e263f7f0-d005-4fb5-ae69-9387c83cc082` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `875dd757-2498-4f3d-970e-a14ab319735f` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `8936599a-8438-488a-a1a4-af017a97a292` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `8abb73de-30b4-450d-b8b9-8e36903b640d` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `92b8b8a2-d60c-4c01-b566-8dcb2bfe10bf` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `93567377-9972-4a60-b677-26b11aa5424e` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `954ad1d1-236a-4acc-a4e7-5c89f73cbcc8` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `95d20ec8-7c2c-4b29-ab53-a303990c8def` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |
| `9620e8ee-1287-413d-976b-9910c06fa2cf` | `SUPERVISOR_RESUME` | 1 | `sandbox unavailable...` |

## 7. Known Artifact Lineage Breaks

- Missing storage paths on disk: **2337**
- Content SHA-256 hash mismatches: **0**
- Broken `derived_from` parent references: **0**

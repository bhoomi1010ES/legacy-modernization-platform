import React, { useState } from 'react';
import { BookOpen, Code, CheckCircle, ArrowRight, Layers } from 'lucide-react';

export const Catalog: React.FC = () => {
  const PATTERNS = [
    {
      id: 'pat-01',
      title: 'Spring Boot REST Controller → NestJS Controller',
      legacy: '@RestController\n@RequestMapping("/api/orders")\npublic class OrderController {\n    @GetMapping("/{id}")\n    public Order getOrder(@PathVariable Long id) {\n        return orderService.findById(id);\n    }\n}',
      target: '@Controller("api/orders")\nexport class OrderController {\n  constructor(private readonly orderService: OrderService) {}\n\n  @Get(":id")\n  async getOrder(@Param("id", ParseIntPipe) id: number): Promise<OrderDto> {\n    return this.orderService.findById(id);\n  }\n}',
      complexity: 'Low',
      category: 'Web API & Routing',
    },
    {
      id: 'pat-02',
      title: 'Spring Data JPA Repository → Prisma ORM',
      legacy: '@Repository\npublic interface OrderRepository extends JpaRepository<Order, Long> {\n    List<Order> findByCustomerIdAndStatus(Long customerId, OrderStatus status);\n}',
      target: '@Injectable()\nexport class OrderRepository {\n  constructor(private readonly prisma: PrismaService) {}\n\n  async findByCustomer(customerId: number, status: OrderStatus) {\n    return this.prisma.order.findMany({\n      where: { customerId, status },\n    });\n  }\n}',
      complexity: 'Medium',
      category: 'Data Access & Persistence',
    },
    {
      id: 'pat-03',
      title: 'Spring Security Filter Chain → NestJS Guard',
      legacy: '@Configuration\n@EnableWebSecurity\npublic class SecurityConfig extends WebSecurityConfigurerAdapter {\n    @Override\n    protected void configure(HttpSecurity http) throws Exception {\n        http.csrf().disable().authorizeRequests().anyRequest().authenticated();\n    }\n}',
      target: '@Injectable()\nexport class JwtAuthGuard extends AuthGuard("jwt") {\n  canActivate(context: ExecutionContext) {\n    return super.canActivate(context);\n  }\n}',
      complexity: 'Medium',
      category: 'Security & Auth',
    },
  ];

  const [selectedPattern, setSelectedPattern] = useState(PATTERNS[0]);

  return (
    <div>
      <div className="page-heading">
        <div>
          <h1>Modernization Pattern Catalog</h1>
          <p className="subtitle">
            Curated architectural transformation templates converting Spring Boot idioms to production TypeScript NestJS standards.
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '24px' }}>
        {/* Pattern List Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {PATTERNS.map((p) => (
            <div
              key={p.id}
              onClick={() => setSelectedPattern(p)}
              style={{
                border: `1px solid ${selectedPattern.id === p.id ? 'var(--primary)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-md)',
                padding: '14px 16px',
                backgroundColor: selectedPattern.id === p.id ? 'var(--accent)' : 'var(--card)',
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
              }}
            >
              <div style={{ fontSize: '10px', color: 'var(--muted-foreground)', fontWeight: 700, textTransform: 'uppercase', marginBottom: '4px' }}>
                {p.category}
              </div>
              <strong style={{ fontSize: '12px', display: 'block', marginBottom: '6px' }}>{p.title}</strong>
              <span className="badge blue" style={{ fontSize: '9px' }}>Complexity: {p.complexity}</span>
            </div>
          ))}
        </div>

        {/* Selected Pattern Comparison View */}
        <div
          style={{
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-md)',
            padding: '24px',
            backgroundColor: 'var(--card)',
            boxShadow: 'var(--shadow-soft)',
          }}
        >
          <div style={{ marginBottom: '20px' }}>
            <span className="badge blue" style={{ marginBottom: '8px' }}>{selectedPattern.category}</span>
            <h2 style={{ fontSize: '18px', fontWeight: 650, marginTop: '4px' }}>{selectedPattern.title}</h2>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div>
              <div style={{ fontSize: '11px', fontWeight: 650, color: 'var(--muted-foreground)', marginBottom: '8px' }}>
                Legacy Java Spring Boot:
              </div>
              <div className="code-panel" style={{ height: '300px' }}>
                {selectedPattern.legacy}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '11px', fontWeight: 650, color: 'var(--primary)', marginBottom: '8px' }}>
                Target TypeScript NestJS Equivalent:
              </div>
              <div className="code-panel" style={{ height: '300px', backgroundColor: 'var(--accent)' }}>
                {selectedPattern.target}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

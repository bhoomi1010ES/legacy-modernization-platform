import React, { useState } from 'react';
import {
  FileCode,
  Folder,
  ChevronRight,
  ChevronDown,
  Terminal,
  Send,
  Play,
  CheckCircle2,
  RefreshCw,
  GitCompare,
} from 'lucide-react';

export const CodeWorkspace: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState('OrderController');
  const [copilotInput, setCopilotInput] = useState('');
  const [messages, setMessages] = useState<Array<{ sender: string; text: string }>>([
    {
      sender: 'CodeWriter Agent',
      text: 'Converted OrderController.java to NestJS. All 6 endpoints pass characterization tests.',
    },
    {
      sender: 'Verifier Agent',
      text: 'Verified 100% behavioral equivalence. Replaced legacy SimpleDateFormat with ISO-8601 UTC pipe.',
    },
  ]);

  const JAVA_CODE = `package com.acme.commerce.controller;

import org.springframework.web.bind.annotation.*;
import org.springframework.beans.factory.annotation.Autowired;
import com.acme.commerce.service.OrderService;
import com.acme.commerce.model.Order;

@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    @Autowired
    private OrderService orderService;

    @GetMapping("/{id}")
    public Order getOrderById(@PathVariable("id") Long id) {
        return orderService.findById(id);
    }

    @PostMapping
    public Order createOrder(@RequestBody Order order) {
        return orderService.createOrder(order);
    }
}`;

  const TYPESCRIPT_CODE = `import { Controller, Get, Post, Body, Param, ParseIntPipe, UseGuards } from '@nestjs/common';
import { OrderService } from '../services/order.service';
import { CreateOrderDto, OrderResponseDto } from '../dto/order.dto';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';

@Controller('api/v1/orders')
@UseGuards(JwtAuthGuard)
export class OrderController {
  constructor(private readonly orderService: OrderService) {}

  @Get(':id')
  async getOrderById(@Param('id', ParseIntPipe) id: number): Promise<OrderResponseDto> {
    return this.orderService.findById(id);
  }

  @Post()
  async createOrder(@Body() dto: CreateOrderDto): Promise<OrderResponseDto> {
    return this.orderService.createOrder(dto);
  }
}`;

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!copilotInput.trim()) return;
    const userMsg = copilotInput;
    setMessages((prev) => [...prev, { sender: 'You (Alex Morgan)', text: userMsg }]);
    setCopilotInput('');

    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          sender: 'CodeWriter Agent',
          text: `Executing instruction: "${userMsg}". Validating contract constraints against OpenAPI specification.`,
        },
      ]);
    }, 600);
  };

  return (
    <div>
      <div className="page-heading" style={{ marginBottom: '16px' }}>
        <div>
          <h1>Multi-Pane Modernization IDE</h1>
          <p className="subtitle">
            Side-by-side legacy Java inspection, target TypeScript generation, and real-time agent copilot collaboration.
          </p>
        </div>
        <div className="heading-actions">
          <button className="button button-secondary button-sm">
            <RefreshCw size={13} />
            <span>Re-verify Diff</span>
          </button>
          <button className="button button-primary button-sm">
            <Play size={13} />
            <span>Run Sandboxed Jest Tests</span>
          </button>
        </div>
      </div>

      {/* 4-Pane IDE Grid */}
      <div className="ide-grid">
        {/* Pane 1: File Tree */}
        <div className="ide-panel">
          <div className="ide-panel-header">
            <span>Project Explorer</span>
            <span className="badge gray" style={{ fontSize: '9px' }}>JOB-0248</span>
          </div>
          <div style={{ padding: '12px 10px', fontSize: '11px', overflowY: 'auto' }}>
            <div style={{ fontWeight: 650, color: 'var(--muted-foreground)', marginBottom: '8px' }}>
              SOURCE (Java 11)
            </div>
            <div style={{ paddingLeft: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  cursor: 'pointer',
                  padding: '4px 6px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: selectedFile === 'OrderController' ? 'var(--accent)' : 'transparent',
                }}
                onClick={() => setSelectedFile('OrderController')}
              >
                <FileCode size={13} color="var(--primary)" />
                <span>OrderController.java</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 6px', color: 'var(--muted-foreground)' }}>
                <FileCode size={13} />
                <span>OrderService.java</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 6px', color: 'var(--muted-foreground)' }}>
                <FileCode size={13} />
                <span>OrderRepository.java</span>
              </div>
            </div>

            <div style={{ fontWeight: 650, color: 'var(--muted-foreground)', marginTop: '16px', marginBottom: '8px' }}>
              TARGET (NestJS TypeScript)
            </div>
            <div style={{ paddingLeft: '8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 6px', color: 'var(--primary)' }}>
                <CheckCircle2 size={13} />
                <span>order.controller.ts</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 6px', color: 'var(--primary)' }}>
                <CheckCircle2 size={13} />
                <span>order.service.ts</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '4px 6px', color: 'var(--primary)' }}>
                <CheckCircle2 size={13} />
                <span>order.dto.ts</span>
              </div>
            </div>
          </div>
        </div>

        {/* Pane 2: Legacy Source Code */}
        <div className="ide-panel">
          <div className="ide-panel-header">
            <span>Legacy: OrderController.java</span>
            <span className="badge gray" style={{ fontSize: '9px' }}>Spring Boot</span>
          </div>
          <div className="code-panel" style={{ border: 'none', borderRadius: 0, height: '100%', overflowY: 'auto' }}>
            {JAVA_CODE}
          </div>
        </div>

        {/* Pane 3: Modern Converted Code */}
        <div className="ide-panel">
          <div className="ide-panel-header">
            <span style={{ color: 'var(--primary)' }}>Converted: order.controller.ts</span>
            <span className="badge green" style={{ fontSize: '9px' }}>100% Equivalence</span>
          </div>
          <div className="code-panel" style={{ border: 'none', borderRadius: 0, height: '100%', overflowY: 'auto', backgroundColor: 'var(--accent)' }}>
            {TYPESCRIPT_CODE}
          </div>
        </div>

        {/* Pane 4: Agent Copilot & Sandbox Terminal */}
        <div className="ide-panel">
          <div className="ide-panel-header">
            <span>Agent Copilot</span>
            <span className="badge purple" style={{ fontSize: '9px' }}>CodeWriter</span>
          </div>

          <div style={{ flex: 1, padding: '12px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '11px' }}>
            {messages.map((m, i) => (
              <div
                key={i}
                style={{
                  padding: '8px 10px',
                  borderRadius: 'var(--radius-sm)',
                  backgroundColor: m.sender.includes('You') ? 'var(--secondary)' : 'var(--purple-surface)',
                  border: '1px solid var(--border)',
                }}
              >
                <div style={{ fontWeight: 650, fontSize: '10px', color: 'var(--muted-foreground)', marginBottom: '3px' }}>
                  {m.sender}
                </div>
                <div>{m.text}</div>
              </div>
            ))}
          </div>

          <form onSubmit={handleSend} style={{ padding: '8px', borderTop: '1px solid var(--border)', display: 'flex', gap: '6px' }}>
            <input
              type="text"
              className="field"
              placeholder="Ask CodeWriter to refine..."
              style={{ padding: '6px 8px', fontSize: '11px' }}
              value={copilotInput}
              onChange={(e) => setCopilotInput(e.target.value)}
            />
            <button type="submit" className="button button-primary button-sm" style={{ padding: '6px 10px' }}>
              <Send size={12} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

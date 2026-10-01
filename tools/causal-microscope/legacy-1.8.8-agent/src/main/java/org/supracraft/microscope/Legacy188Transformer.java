package org.supracraft.microscope;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

public final class Legacy188Transformer implements ClassFileTransformer {
    private enum Kind {
        TICK, EVENT, EVENT_POS, INT_RESULT_POS,
        COMMAND_TRIGGER, PACKET_SEND, WIRE
    }

    private static final class Hook {
        final String id,method,desc,event;
        final Kind kind;
        final int posLocal;
        Hook(String id,String method,String desc,String event,Kind kind,int posLocal) {
            this.id=id; this.method=method; this.desc=desc; this.event=event;
            this.kind=kind; this.posLocal=posLocal;
        }
    }

    private static final Map<String,List<Hook>> HOOKS=new HashMap<String,List<Hook>>();
    static {
        add("net/minecraft/server/MinecraftServer",
            new Hook("server_tick","A","()V","tick",Kind.TICK,-1));
        add("afw",
            new Hook("command_block_neighbor","a","(Ladm;Lcj;Lalz;Lafh;)V",
                "command_block_neighbor",Kind.EVENT_POS,2),
            new Hook("command_block_tick","b","(Ladm;Lcj;Lalz;Ljava/util/Random;)V",
                "command_block_scheduled_tick",Kind.EVENT_POS,2));
        add("adc",
            new Hook("command_trigger","a","(Ladm;)V",
                "command_trigger",Kind.COMMAND_TRIGGER,-1));
        add("adm",
            new Hook("schedule_update","a","(Lcj;Lafh;I)V",
                "scheduled_tick_enqueue",Kind.EVENT_POS,1),
            new Hook("neighbor_notify","c","(Lcj;Lafh;)V",
                "neighbor_notify",Kind.EVENT_POS,1),
            new Hook("block_state_write","a","(Lcj;Lalz;I)Z",
                "block_state_write",Kind.EVENT_POS,1),
            new Hook("redstone_power","c","(Lcj;Lcq;)I",
                "redstone_power",Kind.INT_RESULT_POS,1),
            new Hook("block_power","z","(Lcj;)Z",
                "block_power",Kind.INT_RESULT_POS,1));
        add("ajb",
            new Hook("wire_recompute","a","(Ladm;Lcj;Lcj;Lalz;)Lalz;",
                "wire_recompute",Kind.WIRE,2));
        add("lm",
            new Hook("packet_send","a","(Lff;)V",
                "packet_send",Kind.PACKET_SEND,-1));
    }

    private static void add(String className,Hook... hooks) {
        HOOKS.put(className,new ArrayList<Hook>(Arrays.asList(hooks)));
    }

    @Override
    public byte[] transform(ClassLoader loader,String className,
            Class<?> classBeingRedefined,ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {
        final List<Hook> hooks=HOOKS.get(className);
        if (hooks==null) return null;

        ClassReader reader=new ClassReader(classfileBuffer);
        ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);
        final int[] matched={0};

        ClassVisitor visitor=new ClassVisitor(Opcodes.ASM5,writer) {
            @Override
            public MethodVisitor visitMethod(int access,String name,String desc,
                    String signature,String[] exceptions) {
                MethodVisitor base=super.visitMethod(
                    access,name,desc,signature,exceptions);
                Hook hook=find(hooks,name,desc);
                if (hook==null) return base;
                matched[0]++;
                return new HookVisitor(base,hook);
            }
        };
        reader.accept(visitor,0);
        if (matched[0]!=hooks.size()) {
            TraceRuntime.fatalBinding(
                className,hooks.size(),matched[0]);
        }
        return writer.toByteArray();
    }

    private static Hook find(List<Hook> hooks,String name,String desc) {
        for (Hook hook:hooks) {
            if (hook.method.equals(name) && hook.desc.equals(desc)) return hook;
        }
        return null;
    }

    private static final class HookVisitor extends MethodVisitor {
        private final Hook hook;
        HookVisitor(MethodVisitor mv,Hook hook) {
            super(Opcodes.ASM5,mv);
            this.hook=hook;
        }

        @Override
        public void visitCode() {
            super.visitCode();
            switch (hook.kind) {
                case TICK:
                    call0("tickStart");
                    break;
                case EVENT:
                    event(hook.event);
                    break;
                case EVENT_POS:
                    eventPos(hook.event,hook.posLocal);
                    break;
                case INT_RESULT_POS:
                    eventPos(hook.event+"_query",hook.posLocal);
                    break;
                case COMMAND_TRIGGER:
                    mv.visitVarInsn(Opcodes.ALOAD,0);
                    mv.visitMethodInsn(Opcodes.INVOKESTATIC,
                        runtime(),"commandTriggerStart",
                        "(Ljava/lang/Object;)V",false);
                    break;
                case PACKET_SEND:
                    mv.visitVarInsn(Opcodes.ALOAD,1);
                    mv.visitMethodInsn(Opcodes.INVOKESTATIC,
                        runtime(),"packetSend",
                        "(Ljava/lang/Object;)V",false);
                    break;
                case WIRE:
                    eventPos("wire_recompute_start",hook.posLocal);
                    break;
                default:
                    break;
            }
        }

        @Override
        public void visitInsn(int opcode) {
            if (hook.kind==Kind.TICK && opcode==Opcodes.RETURN) {
                call0("tickEnd");
            } else if (hook.kind==Kind.COMMAND_TRIGGER && opcode==Opcodes.RETURN) {
                mv.visitVarInsn(Opcodes.ALOAD,0);
                mv.visitMethodInsn(Opcodes.INVOKESTATIC,
                    runtime(),"commandTriggerEnd",
                    "(Ljava/lang/Object;)V",false);
            } else if (hook.kind==Kind.WIRE && opcode==Opcodes.ARETURN) {
                eventPos("wire_recompute_end",hook.posLocal);
            } else if (hook.kind==Kind.INT_RESULT_POS && opcode==Opcodes.IRETURN) {
                mv.visitInsn(Opcodes.DUP);
                mv.visitLdcInsn(hook.event+"_result");
                mv.visitInsn(Opcodes.SWAP);
                mv.visitMethodInsn(Opcodes.INVOKESTATIC,
                    runtime(),"eventInt",
                    "(Ljava/lang/String;I)V",false);
            }
            super.visitInsn(opcode);
        }

        private void call0(String name) {
            mv.visitMethodInsn(Opcodes.INVOKESTATIC,runtime(),name,"()V",false);
        }

        private void event(String event) {
            mv.visitLdcInsn(event);
            mv.visitMethodInsn(Opcodes.INVOKESTATIC,
                runtime(),"event","(Ljava/lang/String;)V",false);
        }

        private void eventPos(String event,int local) {
            mv.visitLdcInsn(event);
            mv.visitVarInsn(Opcodes.ALOAD,local);
            mv.visitMethodInsn(Opcodes.INVOKESTATIC,
                runtime(),"eventPos",
                "(Ljava/lang/String;Ljava/lang/Object;)V",false);
        }

        private static String runtime() {
            return "org/supracraft/microscope/TraceRuntime";
        }
    }
}

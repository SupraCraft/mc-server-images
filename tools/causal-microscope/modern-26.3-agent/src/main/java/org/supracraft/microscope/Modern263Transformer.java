package org.supracraft.microscope;

import java.lang.instrument.ClassFileTransformer;
import java.security.MessageDigest;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

public final class Modern263Transformer implements ClassFileTransformer {
    private enum Kind {
        TICK, EVENT_POS, EVENT_POS_WINDOW, INT_RESULT_POS,
        COMMAND_TRIGGER, COMMAND_DISPATCH
    }

    private static final class Hook {
        final String id,method,desc,event;
        final Kind kind;
        final int posArg;
        final int objectArg;
        Hook(String id,String method,String desc,String event,Kind kind,
                int posArg,int objectArg) {
            this.id=id; this.method=method; this.desc=desc; this.event=event;
            this.kind=kind; this.posArg=posArg; this.objectArg=objectArg;
        }
    }

    private static final Map<String,List<Hook>> HOOKS=
        new HashMap<String,List<Hook>>();
    private static final Map<String,String> CLASS_SHA256=
        new HashMap<String,String>();
    private static final int CORE_HOOKS=7;

    static {
        bindClass("net/minecraft/server/MinecraftServer",
            "527d416a4317b9e76d8bbe260afb3af08bdbeb632b4978b47d08ee31ec954402",
            new Hook("server_tick","tickServer",
                "(Ljava/util/function/BooleanSupplier;)V","tick",
                Kind.TICK,-1,-1));
        bindClass("net/minecraft/world/level/Level",
            "68abf43ce4638614ca5d8e7ae185d7e06295ac636c4d4fbc21ee7c3d5e05c4a7",
            new Hook("block_state_write","setBlock",
                "(Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;II)Z",
                "block_state_write",Kind.EVENT_POS,0,-1));
        bindClass("net/minecraft/world/level/block/CommandBlock",
            "2cbe573c4833b44e74a1f41fc83473c1f2a6bc2e7d527b73df5af6b48708ad85",
            new Hook("command_block_neighbor","neighborChanged",
                "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/Block;Lnet/minecraft/world/level/redstone/Orientation;Z)V",
                "command_block_neighbor",Kind.EVENT_POS,2,-1),
            new Hook("command_block_tick","tick",
                "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/core/BlockPos;Lnet/minecraft/util/RandomSource;)V",
                "command_block_scheduled_tick",Kind.EVENT_POS,2,-1),
            new Hook("command_block_execute","execute",
                "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/BaseCommandBlock;Z)V",
                "command_trigger",Kind.COMMAND_TRIGGER,2,3));
        bindClass("net/minecraft/commands/Commands",
            "9307c70b1dce250f869dbf0c633856145718c44b078d656c2dc9c3244176a54e",
            new Hook("command_dispatch","performCommand",
                "(Lcom/mojang/brigadier/ParseResults;Ljava/lang/String;)V",
                "performCommand",Kind.COMMAND_DISPATCH,-1,1),
            new Hook("command_dispatch_prefixed","performPrefixedCommand",
                "(Lnet/minecraft/commands/CommandSourceStack;Ljava/lang/String;)V",
                "performPrefixedCommand",Kind.COMMAND_DISPATCH,-1,1));
    }

    private static final String REDSTONE_CLASS=
        "net/minecraft/world/level/block/RedstoneWireBlock";
    private static final String REDSTONE_CLASS_SHA256=
        "2b0d8320ea23d4178731c60738eab169ae07ec4de5023852870d24ad3c198e01";
    private static final List<Hook> REDSTONE_HOOKS=Arrays.asList(
        new Hook("wire_neighbor_changed","neighborChanged",
            "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/Block;Lnet/minecraft/world/level/redstone/Orientation;Z)V",
            "wire_neighbor_changed",Kind.EVENT_POS,2,-1),
        new Hook("wire_update_power_strength","updatePowerStrength",
            "(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/redstone/Orientation;Z)V",
            "wire_recompute",Kind.EVENT_POS_WINDOW,1,-1),
        new Hook("wire_get_block_signal","getBlockSignal",
            "(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;)I",
            "redstone_power",Kind.INT_RESULT_POS,1,-1)
    );

    private final boolean redstone;
    private final Set<String> bound=
        Collections.synchronizedSet(new HashSet<String>());

    public Modern263Transformer(String sensors) {
        if ("core".equals(sensors)) {
            redstone=false;
        } else if ("core+redstone".equals(sensors)) {
            redstone=true;
        } else {
            TraceRuntime.fatalBinding("sensor_pack:"+sensors,1,0);
            redstone=false;
        }
    }

    private static void bindClass(String className,String sha,Hook... hooks) {
        CLASS_SHA256.put(className,sha);
        HOOKS.put(className,new ArrayList<Hook>(Arrays.asList(hooks)));
    }

    @Override
    public byte[] transform(ClassLoader loader,String className,
            Class<?> classBeingRedefined,ProtectionDomain protectionDomain,
            byte[] classfileBuffer) {
        final List<Hook> coreHooks=HOOKS.get(className);
        final boolean redstoneClass=redstone && REDSTONE_CLASS.equals(className);
        if (coreHooks==null && !redstoneClass) return null;
        final List<Hook> hooks=new ArrayList<Hook>();
        if (coreHooks!=null) hooks.addAll(coreHooks);
        if (redstoneClass) hooks.addAll(REDSTONE_HOOKS);

        String actual=sha256(classfileBuffer);
        String expected=redstoneClass
            ? REDSTONE_CLASS_SHA256 : CLASS_SHA256.get(className);
        if (!expected.equals(actual)) {
            TraceRuntime.fatalBinding(
                "class_sha256:"+className+":"+actual,1,0);
        }

        ClassReader reader=new ClassReader(classfileBuffer);
        ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);
        final int[] matched={0};
        final List<String> ids=new ArrayList<String>();

        ClassVisitor visitor=new ClassVisitor(Opcodes.ASM9,writer) {
            @Override
            public MethodVisitor visitMethod(int access,String name,String desc,
                    String signature,String[] exceptions) {
                MethodVisitor base=super.visitMethod(
                    access,name,desc,signature,exceptions);
                Hook hook=find(hooks,name,desc);
                if (hook==null) return base;
                matched[0]++;
                ids.add(hook.id);
                return new HookVisitor(base,hook,access);
            }
        };
        reader.accept(visitor,0);
        if (matched[0]!=hooks.size()) {
            TraceRuntime.fatalBinding(className,hooks.size(),matched[0]);
        }
        bound.addAll(ids);
        return writer.toByteArray();
    }

    public void verifyComplete() {
        int expected=CORE_HOOKS+(redstone ? REDSTONE_HOOKS.size() : 0);
        if (bound.size()!=expected) {
            TraceRuntime.fatalBinding(
                "modern-26.3-complete-hook-set",expected,bound.size());
        }
    }

    private static Hook find(List<Hook> hooks,String name,String desc) {
        for (Hook hook:hooks) {
            if (hook.method.equals(name) && hook.desc.equals(desc)) return hook;
        }
        return null;
    }

    private static String sha256(byte[] bytes) {
        try {
            MessageDigest md=MessageDigest.getInstance("SHA-256");
            byte[] digest=md.digest(bytes);
            StringBuilder out=new StringBuilder(64);
            for (byte b:digest) out.append(String.format("%02x",b & 0xff));
            return out.toString();
        } catch (Exception exc) {
            TraceRuntime.fatalBinding("class_sha256_runtime",1,0);
            return "";
        }
    }

    private static final class HookVisitor extends MethodVisitor {
        private final Hook hook;
        private final boolean isStatic;

        HookVisitor(MethodVisitor mv,Hook hook,int access) {
            super(Opcodes.ASM9,mv);
            this.hook=hook;
            this.isStatic=(access & Opcodes.ACC_STATIC)!=0;
        }

        @Override
        public void visitCode() {
            super.visitCode();
            switch (hook.kind) {
                case TICK:
                    call0("tickStart");
                    break;
                case EVENT_POS:
                    eventPos(hook.event,argLocal(hook.posArg));
                    break;
                case EVENT_POS_WINDOW:
                    eventPos(hook.event+"_start",argLocal(hook.posArg));
                    break;
                case INT_RESULT_POS:
                    eventPos(hook.event+"_query",argLocal(hook.posArg));
                    break;
                case COMMAND_TRIGGER:
                    mv.visitVarInsn(Opcodes.ALOAD,argLocal(hook.posArg));
                    mv.visitVarInsn(Opcodes.ALOAD,argLocal(hook.objectArg));
                    mv.visitMethodInsn(Opcodes.INVOKESTATIC,runtime(),
                        "commandTriggerStart",
                        "(Ljava/lang/Object;Ljava/lang/Object;)V",false);
                    break;
                case COMMAND_DISPATCH:
                    mv.visitLdcInsn(hook.event);
                    mv.visitVarInsn(Opcodes.ALOAD,argLocal(hook.objectArg));
                    mv.visitMethodInsn(Opcodes.INVOKESTATIC,runtime(),
                        "commandDispatch",
                        "(Ljava/lang/String;Ljava/lang/String;)V",false);
                    break;
                default:
                    break;
            }
        }

        @Override
        public void visitInsn(int opcode) {
            if (hook.kind==Kind.TICK && opcode==Opcodes.RETURN) {
                call0("tickEnd");
            } else if (hook.kind==Kind.EVENT_POS_WINDOW &&
                    opcode==Opcodes.RETURN) {
                eventPos(hook.event+"_end",argLocal(hook.posArg));
            } else if (hook.kind==Kind.INT_RESULT_POS &&
                    opcode==Opcodes.IRETURN) {
                mv.visitInsn(Opcodes.DUP);
                mv.visitLdcInsn(hook.event+"_result");
                mv.visitVarInsn(Opcodes.ALOAD,argLocal(hook.posArg));
                mv.visitMethodInsn(Opcodes.INVOKESTATIC,runtime(),
                    "eventIntPos",
                    "(ILjava/lang/String;Ljava/lang/Object;)V",false);
            } else if (hook.kind==Kind.COMMAND_TRIGGER &&
                    opcode==Opcodes.RETURN) {
                mv.visitVarInsn(Opcodes.ALOAD,argLocal(hook.posArg));
                mv.visitMethodInsn(Opcodes.INVOKESTATIC,runtime(),
                    "commandTriggerEnd",
                    "(Ljava/lang/Object;)V",false);
            }
            super.visitInsn(opcode);
        }

        private int argLocal(int argIndex) {
            Type[] args=Type.getArgumentTypes(hook.desc);
            if (argIndex<0 || argIndex>=args.length) {
                TraceRuntime.fatalBinding(
                    "argument_index:"+hook.id,args.length,argIndex);
            }
            int local=isStatic ? 0 : 1;
            for (int i=0;i<argIndex;i++) local+=args[i].getSize();
            return local;
        }

        private void call0(String name) {
            mv.visitMethodInsn(
                Opcodes.INVOKESTATIC,runtime(),name,"()V",false);
        }

        private void eventPos(String event,int local) {
            mv.visitLdcInsn(event);
            mv.visitVarInsn(Opcodes.ALOAD,local);
            mv.visitMethodInsn(Opcodes.INVOKESTATIC,runtime(),
                "eventPos","(Ljava/lang/String;Ljava/lang/Object;)V",false);
        }

        private static String runtime() {
            return "org/supracraft/microscope/TraceRuntime";
        }
    }
}
